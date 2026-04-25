import { useMemo, useState } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ItemSummary } from '../types';

const MAX_VISIBLE_NODES_PER_CLUSTER = 12;
const FOCUSED_VISIBLE_NODES_PER_CLUSTER = 24;
const CANVAS_WIDTH = 1680;
const CANVAS_HEIGHT = 1120;
const DEFAULT_SCALE = 0.52;
const DEFAULT_OFFSET = { x: -12, y: -4 };
const CENTER_X = CANVAS_WIDTH / 2;
const CENTER_Y = CANVAS_HEIGHT / 2;

type OrbitLod = 'dot' | 'thumb' | 'preview';

type OrbitNode = {
  item: ItemSummary;
  imagePath: string;
  lod: 'dot' | 'thumb' | 'preview';
  x: number;
  y: number;
  size: number;
  angle: number;
  ringIndex: number;
  laneIndex: number;
};

type OrbitCluster = ClusterRecord & {
  x: number;
  y: number;
  radius: number;
  nodes: OrbitNode[];
  hiddenCount: number;
  inactive: boolean;
};

function clusterPosition(index: number, total: number, count: number, focused: boolean) {
  if (focused) return { x: CENTER_X, y: CENTER_Y + 22 };
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

function getOrbitImagePath(item: ItemSummary, lod: OrbitLod) {
  if (lod === 'preview') return item.first_image?.preview_path || item.first_image?.thumb_path || '';
  if (lod === 'thumb') return item.first_image?.thumb_path || item.first_image?.preview_path || '';
  return '';
}

function scoreItems(items: ItemSummary[]) {
  return [...items].sort((a, b) => {
    if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
    if ((b.rating || 0) !== (a.rating || 0)) return (b.rating || 0) - (a.rating || 0);
    const aImage = getOrbitImagePath(a, 'thumb') ? 1 : 0;
    const bImage = getOrbitImagePath(b, 'thumb') ? 1 : 0;
    if (aImage !== bImage) return bImage - aImage;
    return a.title.localeCompare(b.title, 'zh-Hant');
  });
}

function orbitLod(scale: number, focused: boolean): OrbitLod {
  if (!focused && scale < 0.54) return 'dot';
  if (focused || scale > 0.86) return 'preview';
  return 'thumb';
}

function buildOrbit(clusters: ClusterRecord[], items: ItemSummary[], focusedClusterId: string | undefined, scale: number): OrbitCluster[] {
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
      const inactive = !!focusedClusterId && !focused;
      const cap = focused ? FOCUSED_VISIBLE_NODES_PER_CLUSTER : MAX_VISIBLE_NODES_PER_CLUSTER;
      const allItems = scoreItems(itemsByCluster.get(cluster.id) || []);
      const visible = inactive ? [] : allItems.slice(0, cap);
      const pos = clusterPosition(index, arr.length, cluster.count, focused);
      const radius = Math.max(136, Math.min(282, 106 + Math.sqrt(cluster.count) * 14 + (focused ? 82 : 0)));
      const lod = orbitLod(scale, focused);
      const ringCapacity = focused ? 8 : 6;
      const ringGap = focused ? 54 : 38;
      const nodes = visible.map((item, nodeIndex) => {
        const ringIndex = Math.floor(nodeIndex / ringCapacity);
        const laneIndex = nodeIndex % ringCapacity;
        const nodesInRing = Math.min(ringCapacity, visible.length - ringIndex * ringCapacity);
        const laneOffset = ringIndex % 2 ? Math.PI / Math.max(6, nodesInRing) : 0;
        const angle = (-Math.PI / 2) + (laneIndex / Math.max(1, nodesInRing)) * Math.PI * 2 + laneOffset;
        const nodeRadius = radius + ringIndex * ringGap;
        const baseSize = lod === 'dot' ? 28 : focused ? 112 : 86;
        const size = Math.round(Math.max(22, Math.min(focused ? 142 : 112, baseSize + (item.favorite ? 12 : 0) + (item.rating || 0) * 2 - ringIndex * 5)));
        return {
          item,
          imagePath: getOrbitImagePath(item, lod),
          lod,
          x: pos.x + Math.cos(angle) * nodeRadius,
          y: pos.y + Math.sin(angle) * nodeRadius * 0.74,
          size,
          angle,
          ringIndex,
          laneIndex,
        };
      });
      return {
        ...cluster,
        x: pos.x,
        y: pos.y,
        radius,
        nodes,
        hiddenCount: inactive ? 0 : Math.max(0, allItems.length - visible.length),
        inactive,
      };
    });
}

export default function ExploreView({
  clusters,
  items,
  focusedClusterId,
  onFocusCluster,
  onOpenClusterCards,
  onOpen,
}: {
  clusters: ClusterRecord[];
  items: ItemSummary[];
  focusedClusterId?: string;
  onFocusCluster: (c: ClusterRecord) => void;
  onOpenClusterCards: (c: ClusterRecord) => void;
  onOpen: (id: string) => void;
}) {
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [offset, setOffset] = useState(DEFAULT_OFFSET);
  const [dragStart, setDragStart] = useState<{ x: number; y: number; ox: number; oy: number }>();
  const orbit = useMemo(() => buildOrbit(clusters, items, focusedClusterId, scale), [clusters, items, focusedClusterId, scale]);
  const focusedCluster = orbit.find(cluster => cluster.id === focusedClusterId);

  if (!clusters.length) {
    return (
      <div className="empty">
        <h2>No clusters yet</h2>
        <p>Import OpenNana or add your first prompt to start exploring.</p>
      </div>
    );
  }

  const reset = () => { setScale(DEFAULT_SCALE); setOffset(DEFAULT_OFFSET); };
  const handleOpenClusterCards = (cluster: OrbitCluster) => onOpenClusterCards(cluster);

  return (
    <section className={`spatial-orbit-map ${focusedClusterId ? 'is-focused' : ''}`} aria-label="Prompt clusters spatial orbit map">
      <div className="orbit-toolbar" aria-label="Orbit map controls">
        <button onClick={() => setScale(s => Math.max(0.42, s - 0.08))} aria-label="Zoom out"><Minus size={16} /></button>
        <button onClick={() => setScale(s => Math.min(1.45, s + 0.08))} aria-label="Zoom in"><Plus size={16} /></button>
        <button onClick={reset}><RotateCcw size={16} /> Reset</button>
        <span>{focusedClusterId ? `${FOCUSED_VISIBLE_NODES_PER_CLUSTER} focused nodes · rings ordered` : `${MAX_VISIBLE_NODES_PER_CLUSTER} shown per cluster · adaptive LOD`}</span>
      </div>
      {focusedCluster && (
        <div className="orbit-focus-panel">
          <strong>{focusedCluster.name}</strong>
          <span>{focusedCluster.count} references · {focusedCluster.nodes.length} visible</span>
          <button onClick={() => handleOpenClusterCards(focusedCluster)}>Open as Cards</button>
        </div>
      )}
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
              className={`orbit-cluster-label ${cluster.id === focusedClusterId ? 'focused' : ''} ${cluster.inactive ? 'inactive' : ''}`}
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
              className={`orbit-node ${node.item.favorite ? 'favorite' : ''} lod-${node.lod}`}
              style={{ left: node.x, top: node.y, width: node.size, height: Math.round(node.size * (node.lod === 'dot' ? 1 : 1.25)), transform: `translate(-50%, -50%) rotate(${Math.sin(node.angle) * 5}deg)` }}
              onClick={(event) => { event.stopPropagation(); onOpen(node.item.id); }}
              title={node.item.title}
              aria-label={node.item.title}
            >
              {node.lod !== 'dot' && node.imagePath ? <img src={mediaUrl(node.imagePath)} alt={node.item.title} loading="lazy" decoding="async" /> : <span className="node-placeholder" />}
              {node.lod !== 'dot' && <span>{node.item.title}</span>}
            </button>
          )))}
        </div>
      </div>
    </section>
  );
}
