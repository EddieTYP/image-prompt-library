import { useMemo, useState } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ItemSummary } from '../types';

const MAX_VISIBLE_NODES_PER_CLUSTER = 12;
const FOCUSED_VISIBLE_NODES_PER_CLUSTER = 24;
const CANVAS_WIDTH = 1680;
const CANVAS_HEIGHT = 1120;
const DEFAULT_SCALE = 0.60;
const DEFAULT_OFFSET = { x: -26, y: -12 };
const CENTER_X = CANVAS_WIDTH / 2;
const CENTER_Y = CANVAS_HEIGHT / 2;

type OrbitNode = {
  item: ItemSummary;
  imagePath: string;
  x: number;
  y: number;
  size: number;
  angle: number;
};

type OrbitCluster = ClusterRecord & {
  x: number;
  y: number;
  radius: number;
  nodes: OrbitNode[];
  hiddenCount: number;
};

function clusterPosition(index: number, total: number, count: number) {
  if (index === 0) return { x: CENTER_X, y: CENTER_Y + 10 };
  const ring = index <= 6 ? 1 : 2;
  const ringIndex = ring === 1 ? index - 1 : index - 7;
  const ringCount = ring === 1 ? Math.min(6, total - 1) : Math.max(1, total - 7);
  const angle = (-Math.PI / 2) + (ringIndex / ringCount) * Math.PI * 2 + (ring === 2 ? Math.PI / 7 : 0);
  const distance = ring === 1 ? 350 : 560;
  const weightNudge = Math.min(70, Math.sqrt(count) * 7);
  return {
    x: CENTER_X + Math.cos(angle) * (distance + weightNudge),
    y: CENTER_Y + Math.sin(angle) * (distance * 0.58 + weightNudge * 0.42),
  };
}

function nodePath(item: ItemSummary) {
  return item.first_image?.thumb_path || item.first_image?.preview_path || item.first_image?.original_path || '';
}

function scoreItems(items: ItemSummary[]) {
  return [...items].sort((a, b) => {
    if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
    if ((b.rating || 0) !== (a.rating || 0)) return (b.rating || 0) - (a.rating || 0);
    const aImage = nodePath(a) ? 1 : 0;
    const bImage = nodePath(b) ? 1 : 0;
    if (aImage !== bImage) return bImage - aImage;
    return a.title.localeCompare(b.title, 'zh-Hant');
  });
}

function buildOrbit(clusters: ClusterRecord[], items: ItemSummary[], focusedClusterId?: string): OrbitCluster[] {
  const itemsByCluster = new Map<string, ItemSummary[]>();
  for (const item of items) {
    const id = item.cluster?.id;
    if (!id) continue;
    const list = itemsByCluster.get(id) || [];
    list.push(item);
    itemsByCluster.set(id, list);
  }

  return [...clusters]
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hant'))
    .map((cluster, index, arr) => {
      const focused = cluster.id === focusedClusterId;
      const cap = focused ? FOCUSED_VISIBLE_NODES_PER_CLUSTER : MAX_VISIBLE_NODES_PER_CLUSTER;
      const allItems = scoreItems(itemsByCluster.get(cluster.id) || []);
      const visible = allItems.slice(0, cap);
      const pos = clusterPosition(index, arr.length, cluster.count);
      const radius = Math.max(122, Math.min(228, 96 + Math.sqrt(cluster.count) * 15 + (focused ? 42 : 0)));
      const nodes = visible.map((item, nodeIndex) => {
        const angle = (-Math.PI / 2) + (nodeIndex / Math.max(1, visible.length)) * Math.PI * 2 + ((nodeIndex % 2) * 0.16);
        const lane = nodeIndex % 3;
        const nodeRadius = radius + lane * 34;
        const size = Math.round(Math.max(74, Math.min(128, 88 + (item.favorite ? 18 : 0) + (item.rating || 0) * 3 - lane * 4)));
        return {
          item,
          imagePath: nodePath(item),
          x: pos.x + Math.cos(angle) * nodeRadius,
          y: pos.y + Math.sin(angle) * nodeRadius * 0.72,
          size,
          angle,
        };
      });
      return {
        ...cluster,
        x: pos.x,
        y: pos.y,
        radius,
        nodes,
        hiddenCount: Math.max(0, allItems.length - visible.length),
      };
    });
}

export default function ExploreView({
  clusters,
  items,
  focusedClusterId,
  onFocusCluster,
  onOpen,
}: {
  clusters: ClusterRecord[];
  items: ItemSummary[];
  focusedClusterId?: string;
  onFocusCluster: (c: ClusterRecord) => void;
  onOpen: (id: string) => void;
}) {
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [offset, setOffset] = useState(DEFAULT_OFFSET);
  const [dragStart, setDragStart] = useState<{ x: number; y: number; ox: number; oy: number }>();
  const orbit = useMemo(() => buildOrbit(clusters, items, focusedClusterId), [clusters, items, focusedClusterId]);

  if (!clusters.length) {
    return (
      <div className="empty">
        <h2>No clusters yet</h2>
        <p>Import OpenNana or add your first prompt to start exploring.</p>
      </div>
    );
  }

  const reset = () => { setScale(DEFAULT_SCALE); setOffset(DEFAULT_OFFSET); };

  return (
    <section className="spatial-orbit-map" aria-label="Prompt clusters spatial orbit map">
      <div className="orbit-toolbar" aria-label="Orbit map controls">
        <button onClick={() => setScale(s => Math.max(0.42, s - 0.08))} aria-label="Zoom out"><Minus size={16} /></button>
        <button onClick={() => setScale(s => Math.min(1.45, s + 0.08))} aria-label="Zoom in"><Plus size={16} /></button>
        <button onClick={reset}><RotateCcw size={16} /> Reset</button>
        <span>{MAX_VISIBLE_NODES_PER_CLUSTER} shown per cluster · favorites first</span>
      </div>
      <div
        className="orbit-viewport"
        onWheel={(event) => {
          event.preventDefault();
          setScale(s => Math.max(0.42, Math.min(1.45, s + (event.deltaY < 0 ? 0.06 : -0.06))));
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setDragStart({ x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y });
        }}
        onPointerMove={(event) => {
          if (!dragStart) return;
          setOffset({ x: dragStart.ox + event.clientX - dragStart.x, y: dragStart.oy + event.clientY - dragStart.y });
        }}
        onPointerUp={() => setDragStart(undefined)}
        onPointerCancel={() => setDragStart(undefined)}
      >
        <div
          className="orbit-canvas"
          style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `translate(-50%, -50%) translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})` }}
        >
          <svg className="orbit-links" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} aria-hidden="true">
            {orbit.flatMap(cluster => cluster.nodes.map(node => (
              <line key={`${cluster.id}-${node.item.id}-link`} x1={cluster.x} y1={cluster.y} x2={node.x} y2={node.y} />
            )))}
          </svg>
          {orbit.map(cluster => (
            <button
              key={cluster.id}
              className={`orbit-cluster-label ${cluster.id === focusedClusterId ? 'focused' : ''}`}
              style={{ left: cluster.x, top: cluster.y }}
              onClick={(event) => { event.stopPropagation(); onFocusCluster(cluster); }}
              title={`${cluster.count} references`}
            >
              <strong>{cluster.name}</strong>
              <span>{cluster.count}</span>
              {cluster.hiddenCount > 0 && <em>+{cluster.hiddenCount} more</em>}
            </button>
          ))}
          {orbit.flatMap(cluster => cluster.nodes.map(node => (
            <button
              key={`${cluster.id}-${node.item.id}`}
              className={`orbit-node ${node.item.favorite ? 'favorite' : ''}`}
              style={{ left: node.x, top: node.y, width: node.size, height: Math.round(node.size * 1.25), transform: `translate(-50%, -50%) rotate(${Math.sin(node.angle) * 8}deg)` }}
              onClick={(event) => { event.stopPropagation(); onOpen(node.item.id); }}
              title={node.item.title}
            >
              {node.imagePath ? <img src={mediaUrl(node.imagePath)} alt={node.item.title} loading="lazy" decoding="async" /> : <span className="node-placeholder" />}
              <span>{node.item.title}</span>
            </button>
          )))}
        </div>
      </div>
    </section>
  );
}
