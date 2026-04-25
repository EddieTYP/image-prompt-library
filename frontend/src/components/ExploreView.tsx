import { useMemo, useState, type PointerEvent } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ItemSummary } from '../types';

const CANVAS_WIDTH = 2200;
const CANVAS_HEIGHT = 1500;
const DEFAULT_SCALE = 0.48;
const DEFAULT_OFFSET = { x: -18, y: -10 };
const CENTER_X = CANVAS_WIDTH / 2;
const CENTER_Y = CANVAS_HEIGHT / 2;
const TAP_DRAG_THRESHOLD = 7;
const CLUSTER_CARD_WIDTH = 178;
const CLUSTER_CARD_HEIGHT = 96;
const GLOBAL_THUMB_WIDTH = 104;
const GLOBAL_THUMB_HEIGHT = 130;
const FOCUS_THUMB_WIDTH = 118;
const FOCUS_THUMB_HEIGHT = 148;
const RELAXATION_ITERATIONS = 90;
const REPULSION_STRENGTH = 0.34;
const CLUSTER_REPULSION_STRENGTH = 0.42;
const SPRING_STRENGTH = 0.035;
const RELAXATION_DAMPING = 0.78;

type TapTarget =
  | { type: 'cluster'; cluster: ConstellationCluster }
  | { type: 'item'; item: ItemSummary }
  | undefined;

type TapState = {
  pointerId: number;
  x: number;
  y: number;
  dragged: boolean;
  tapTarget: TapTarget;
};

type DragState = { pointerId: number; x: number; y: number; ox: number; oy: number };

type ConstellationNode = {
  item: ItemSummary;
  imagePath: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle: number;
  index: number;
};

type ConstellationCluster = ClusterRecord & {
  x: number;
  y: number;
  width: number;
  height: number;
  nodes: ConstellationNode[];
  hiddenCount: number;
  inactive: boolean;
};

type CollisionBox = { x: number; y: number; width: number; height: number };
type RelaxedNode = ConstellationNode & { anchorX: number; anchorY: number; vx: number; vy: number };

function getConstellationImagePath(item: ItemSummary) {
  return item.first_image?.thumb_path || item.first_image?.preview_path || '';
}

function scoreItems(items: ItemSummary[]) {
  return [...items].sort((a, b) => {
    if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
    if ((b.rating || 0) !== (a.rating || 0)) return (b.rating || 0) - (a.rating || 0);
    const aImage = getConstellationImagePath(a) ? 1 : 0;
    const bImage = getConstellationImagePath(b) ? 1 : 0;
    if (aImage !== bImage) return bImage - aImage;
    return a.title.localeCompare(b.title, 'zh-Hant');
  });
}

function clusterPosition(index: number, total: number, count: number, focused: boolean) {
  if (focused) return centerFocusedCluster();
  if (total <= 1) return { x: CENTER_X, y: CENTER_Y };
  const ring = index < 6 ? 0 : 1;
  const indexInRing = ring === 0 ? index : index - 6;
  const ringCount = ring === 0 ? Math.min(6, total) : Math.max(1, total - 6);
  const angle = (-Math.PI / 2) + (indexInRing / ringCount) * Math.PI * 2 + (ring ? Math.PI / 9 : 0);
  const distance = ring === 0 ? 470 : 760;
  const nudge = Math.min(70, Math.sqrt(count) * 6);
  return {
    x: CENTER_X + Math.cos(angle) * (distance + nudge),
    y: CENTER_Y + Math.sin(angle) * (distance * 0.68 + nudge * 0.36),
  };
}

function centerFocusedCluster() {
  return { x: CENTER_X, y: CENTER_Y };
}

function allocateGlobalThumbnailBudget(clusters: ClusterRecord[], itemsByCluster: Map<string, ItemSummary[]>, budget: number) {
  const allocations = new Map<string, number>();
  const nonEmpty = clusters.filter(cluster => (itemsByCluster.get(cluster.id) || []).length > 0);
  if (!nonEmpty.length || budget <= 0) return allocations;

  const minimumAllocation = Math.max(1, Math.min(2, Math.floor(budget / nonEmpty.length) || 1));
  let used = 0;
  for (const cluster of nonEmpty) {
    const count = itemsByCluster.get(cluster.id)?.length || 0;
    const allocation = Math.min(minimumAllocation, count, Math.max(0, budget - used));
    allocations.set(cluster.id, allocation);
    used += allocation;
  }

  let remaining = Math.max(0, budget - used);
  const totalRemainderDemand = nonEmpty.reduce((sum, cluster) => {
    const count = itemsByCluster.get(cluster.id)?.length || 0;
    return sum + Math.max(0, count - (allocations.get(cluster.id) || 0));
  }, 0);

  for (const cluster of nonEmpty) {
    if (remaining <= 0 || totalRemainderDemand <= 0) break;
    const count = itemsByCluster.get(cluster.id)?.length || 0;
    const current = allocations.get(cluster.id) || 0;
    const demand = Math.max(0, count - current);
    const share = Math.floor((demand / totalRemainderDemand) * remaining);
    const add = Math.min(demand, share);
    allocations.set(cluster.id, current + add);
  }

  let distributed = Array.from(allocations.values()).reduce((sum, value) => sum + value, 0);
  while (distributed < budget) {
    let changed = false;
    for (const cluster of nonEmpty) {
      if (distributed >= budget) break;
      const count = itemsByCluster.get(cluster.id)?.length || 0;
      const current = allocations.get(cluster.id) || 0;
      if (current < count) {
        allocations.set(cluster.id, current + 1);
        distributed += 1;
        changed = true;
      }
    }
    if (!changed) break;
  }

  return allocations;
}

function doesCollide(candidate: CollisionBox, boxes: CollisionBox[]) {
  const padding = 12;
  return boxes.some(box => Math.abs(candidate.x - box.x) < (candidate.width + box.width) / 2 + padding && Math.abs(candidate.y - box.y) < (candidate.height + box.height) / 2 + padding);
}

function overlapVector(a: CollisionBox, b: CollisionBox) {
  const minX = (a.width + b.width) / 2 + 14;
  const minY = (a.height + b.height) / 2 + 14;
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const overlapX = minX - Math.abs(dx);
  const overlapY = minY - Math.abs(dy);
  if (overlapX <= 0 || overlapY <= 0) return { x: 0, y: 0 };
  const directionX = dx === 0 ? 1 : Math.sign(dx);
  const directionY = dy === 0 ? 1 : Math.sign(dy);
  if (overlapX < overlapY) return { x: directionX * overlapX, y: 0 };
  return { x: 0, y: directionY * overlapY };
}

function boxForNode(node: Pick<ConstellationNode, 'x' | 'y' | 'width' | 'height'>): CollisionBox {
  return { x: node.x, y: node.y, width: node.width, height: node.height };
}

function clampRelaxedNode(node: RelaxedNode) {
  const marginX = Math.max(70, node.width / 2 + 18);
  const marginY = Math.max(80, node.height / 2 + 18);
  node.x = Math.max(marginX, Math.min(CANVAS_WIDTH - marginX, node.x));
  node.y = Math.max(marginY, Math.min(CANVAS_HEIGHT - marginY, node.y));
}

function repelAgainstClusterHubs(node: RelaxedNode, hubs: CollisionBox[]) {
  for (const hub of hubs) {
    const vector = overlapVector(boxForNode(node), hub);
    node.vx += vector.x * CLUSTER_REPULSION_STRENGTH;
    node.vy += vector.y * CLUSTER_REPULSION_STRENGTH;
  }
}

function relaxConstellationNodes(nodes: ConstellationNode[], center: { x: number; y: number }, hubs: CollisionBox[]) {
  const relaxed: RelaxedNode[] = nodes.map(node => ({ ...node, anchorX: node.x, anchorY: node.y, vx: 0, vy: 0 }));
  for (let iteration = 0; iteration < RELAXATION_ITERATIONS; iteration += 1) {
    for (let i = 0; i < relaxed.length; i += 1) {
      const a = relaxed[i];
      a.vx += (a.anchorX - a.x) * SPRING_STRENGTH;
      a.vy += (a.anchorY - a.y) * SPRING_STRENGTH;
      repelAgainstClusterHubs(a, hubs);
      for (let j = i + 1; j < relaxed.length; j += 1) {
        const b = relaxed[j];
        const vector = overlapVector(boxForNode(a), boxForNode(b));
        if (!vector.x && !vector.y) continue;
        a.vx += vector.x * REPULSION_STRENGTH;
        a.vy += vector.y * REPULSION_STRENGTH;
        b.vx -= vector.x * REPULSION_STRENGTH;
        b.vy -= vector.y * REPULSION_STRENGTH;
      }
    }
    for (const node of relaxed) {
      node.x += node.vx;
      node.y += node.vy;
      node.vx *= RELAXATION_DAMPING;
      node.vy *= RELAXATION_DAMPING;
      clampRelaxedNode(node);
    }
  }
  return relaxed
    .map(node => ({
      item: node.item,
      imagePath: node.imagePath,
      x: node.x,
      y: node.y,
      width: node.width,
      height: node.height,
      angle: node.angle,
      index: node.index,
    }))
    .sort((a, b) => Math.hypot(a.x - center.x, a.y - center.y) - Math.hypot(b.x - center.x, b.y - center.y));
}

function settleCollisionAwarePositions(seeds: ConstellationNode[], center: { x: number; y: number }, reserved: CollisionBox[]) {
  const staticObstacles = [...reserved];
  const placed: CollisionBox[] = [];
  const spiralStep = 16;
  const initiallySettled = seeds.map(seed => {
    let x = seed.x;
    let y = seed.y;
    let box = { x, y, width: seed.width, height: seed.height };
    for (let attempt = 0; attempt < 70 && doesCollide(box, [...staticObstacles, ...placed]); attempt += 1) {
      const angle = seed.angle + attempt * 0.76;
      const radius = spiralStep * (1 + attempt * 0.34);
      x = seed.x + Math.cos(angle) * radius;
      y = seed.y + Math.sin(angle) * radius;
      x = Math.max(70, Math.min(CANVAS_WIDTH - 70, x));
      y = Math.max(80, Math.min(CANVAS_HEIGHT - 80, y));
      box = { x, y, width: seed.width, height: seed.height };
    }
    placed.push(box);
    return { ...seed, x, y };
  });
  const relaxed = relaxConstellationNodes(initiallySettled, center, staticObstacles);
  reserved.push(...relaxed.map(boxForNode));
  return relaxed;
}

function buildClusterNodes(allItems: ItemSummary[], cap: number, pos: { x: number; y: number }, focused: boolean, reserved: CollisionBox[]) {
  const visible = scoreItems(allItems).slice(0, cap);
  const width = focused ? FOCUS_THUMB_WIDTH : GLOBAL_THUMB_WIDTH;
  const height = focused ? FOCUS_THUMB_HEIGHT : GLOBAL_THUMB_HEIGHT;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const baseRadius = focused ? 188 : 146;
  const radiusStep = focused ? 19 : 14;
  const seeds = visible.map((item, index) => {
    const angle = index * goldenAngle - Math.PI / 2;
    const ring = Math.floor(Math.sqrt(index));
    const radius = baseRadius + ring * radiusStep + (index % 5) * 4;
    return {
      item,
      imagePath: getConstellationImagePath(item),
      x: pos.x + Math.cos(angle) * radius,
      y: pos.y + Math.sin(angle) * radius * (focused ? 0.9 : 0.82),
      width,
      height,
      angle,
      index,
    };
  });
  return settleCollisionAwarePositions(seeds, pos, reserved);
}

function buildConstellation(clusters: ClusterRecord[], items: ItemSummary[], focusedClusterId: string | undefined, globalThumbnailBudget: number, focusThumbnailBudget: number): ConstellationCluster[] {
  const itemsByCluster = new Map<string, ItemSummary[]>();
  for (const item of items) {
    const id = item.cluster?.id;
    if (!id) continue;
    const list = itemsByCluster.get(id) || [];
    list.push(item);
    itemsByCluster.set(id, list);
  }

  const sortedClusters = [...clusters].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hant'));
  const allocations = allocateGlobalThumbnailBudget(sortedClusters, itemsByCluster, globalThumbnailBudget);
  const clusterPositions = new Map<string, { x: number; y: number }>();
  sortedClusters.forEach((cluster, index) => clusterPositions.set(cluster.id, clusterPosition(index, sortedClusters.length, cluster.count, cluster.id === focusedClusterId)));
  const sharedCollisionBoxes: CollisionBox[] = sortedClusters.map(cluster => {
    const pos = clusterPositions.get(cluster.id) || centerFocusedCluster();
    return { x: pos.x, y: pos.y, width: CLUSTER_CARD_WIDTH + 30, height: CLUSTER_CARD_HEIGHT + 28 };
  });

  return sortedClusters.map((cluster) => {
    const focused = cluster.id === focusedClusterId;
    const inactive = !!focusedClusterId && !focused;
    const allItems = itemsByCluster.get(cluster.id) || [];
    const pos = clusterPositions.get(cluster.id) || centerFocusedCluster();
    const cap = focused ? focusThumbnailBudget : (allocations.get(cluster.id) || 0);
    const nodes = inactive ? [] : buildClusterNodes(allItems, cap, pos, focused, sharedCollisionBoxes);
    return {
      ...cluster,
      x: pos.x,
      y: pos.y,
      width: CLUSTER_CARD_WIDTH,
      height: CLUSTER_CARD_HEIGHT,
      nodes,
      hiddenCount: inactive ? 0 : Math.max(0, allItems.length - nodes.length),
      inactive,
    };
  });
}

export default function ExploreView({
  clusters,
  items,
  focusedClusterId,
  globalThumbnailBudget,
  focusThumbnailBudget,
  onFocusCluster,
  onOpenClusterCards,
  onOpen,
}: {
  clusters: ClusterRecord[];
  items: ItemSummary[];
  focusedClusterId?: string;
  globalThumbnailBudget: number;
  focusThumbnailBudget: number;
  onFocusCluster: (c: ClusterRecord) => void;
  onOpenClusterCards: (c: ClusterRecord) => void;
  onOpen: (id: string) => void;
}) {
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [offset, setOffset] = useState(DEFAULT_OFFSET);
  const [dragStart, setDragStart] = useState<DragState>();
  const [tapState, setTapState] = useState<TapState>();
  const constellation = useMemo(
    () => buildConstellation(clusters, items, focusedClusterId, globalThumbnailBudget, focusThumbnailBudget),
    [clusters, items, focusedClusterId, globalThumbnailBudget, focusThumbnailBudget],
  );
  const focusedCluster = constellation.find(cluster => cluster.id === focusedClusterId);

  if (!clusters.length) {
    return (
      <div className="empty">
        <h2>No clusters yet</h2>
        <p>Import OpenNana or add your first prompt to start exploring.</p>
      </div>
    );
  }

  const reset = () => { setScale(DEFAULT_SCALE); setOffset(DEFAULT_OFFSET); };
  const handleOpenClusterCards = (cluster: ConstellationCluster) => onOpenClusterCards(cluster);
  const beginTap = (event: PointerEvent<HTMLElement>, tapTarget: TapTarget) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setTapState({ pointerId: event.pointerId, x: event.clientX, y: event.clientY, dragged: false, tapTarget });
  };
  const moveTap = (event: PointerEvent<HTMLElement>) => {
    if (!tapState || tapState.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - tapState.x, event.clientY - tapState.y);
    if (distance > TAP_DRAG_THRESHOLD && !tapState.dragged) setTapState({ ...tapState, dragged: true });
  };
  const endTap = (event: PointerEvent<HTMLElement>) => {
    if (!tapState || tapState.pointerId !== event.pointerId) return;
    event.stopPropagation();
    const target = tapState.tapTarget;
    const shouldActivate = !tapState.dragged;
    setTapState(undefined);
    if (!shouldActivate || !target) return;
    if (target.type === 'cluster') onFocusCluster(target.cluster);
    if (target.type === 'item') onOpen(target.item.id);
  };

  return (
    <section className={`thumbnail-constellation ${focusedClusterId ? 'is-focused' : ''}`} aria-label="Prompt clusters thumbnail constellation graph">
      <div className="constellation-toolbar" aria-label="Constellation controls">
        <button onClick={() => setScale(s => Math.max(0.42, s - 0.08))} aria-label="Zoom out"><Minus size={16} /></button>
        <button onClick={() => setScale(s => Math.min(1.35, s + 0.08))} aria-label="Zoom in"><Plus size={16} /></button>
        <button onClick={reset}><RotateCcw size={16} /> Reset</button>
        <span>{focusedClusterId ? `${focusThumbnailBudget} focus thumbnail budget` : `${globalThumbnailBudget} global thumbnail budget`}</span>
      </div>
      {focusedCluster && (
        <div className="constellation-focus-panel">
          <strong>{focusedCluster.name}</strong>
          <span>{focusedCluster.count} references · {focusedCluster.nodes.length} visible</span>
          <button onClick={() => handleOpenClusterCards(focusedCluster)}>Open as Cards</button>
        </div>
      )}
      <div
        className="constellation-viewport"
        onWheel={(event) => {
          event.preventDefault();
          setScale(s => Math.max(0.42, Math.min(1.35, s + (event.deltaY < 0 ? 0.06 : -0.06))));
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setDragStart({ pointerId: event.pointerId, x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y });
        }}
        onPointerMove={(event) => {
          if (!dragStart || dragStart.pointerId !== event.pointerId) return;
          setOffset({ x: dragStart.ox + event.clientX - dragStart.x, y: dragStart.oy + event.clientY - dragStart.y });
        }}
        onPointerUp={() => setDragStart(undefined)}
        onPointerCancel={() => { setDragStart(undefined); setTapState(undefined); }}
      >
        <div
          className="constellation-canvas"
          style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `translate(-50%, -50%) translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})` }}
        >
          <svg className="constellation-links" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} aria-hidden="true">
            {constellation.flatMap(cluster => cluster.nodes.map(node => (
              <line key={`${cluster.id}-${node.item.id}-link`} x1={cluster.x} y1={cluster.y} x2={node.x} y2={node.y} />
            )))}
          </svg>
          {constellation.map(cluster => (
            <button
              key={cluster.id}
              className={`constellation-cluster-card ${cluster.id === focusedClusterId ? 'focused' : ''} ${cluster.inactive ? 'inactive' : ''}`}
              style={{ left: cluster.x, top: cluster.y, width: cluster.width, minHeight: cluster.height }}
              onPointerDown={(event) => beginTap(event, { type: 'cluster', cluster })}
              onPointerMove={moveTap}
              onPointerUp={endTap}
              onPointerCancel={() => setTapState(undefined)}
              title={`${cluster.count} references`}
            >
              <strong>{cluster.name}</strong>
              <span>{cluster.count} references</span>
              {cluster.hiddenCount > 0 && <em>+{cluster.hiddenCount} more</em>}
            </button>
          ))}
          {constellation.flatMap(cluster => cluster.nodes.map(node => (
            <button
              key={`${cluster.id}-${node.item.id}`}
              className={`constellation-thumb-card ${node.item.favorite ? 'favorite' : ''}`}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height, transform: `translate(-50%, -50%) rotate(${Math.sin(node.angle) * 3.5}deg)` }}
              onPointerDown={(event) => beginTap(event, { type: 'item', item: node.item })}
              onPointerMove={moveTap}
              onPointerUp={endTap}
              onPointerCancel={() => setTapState(undefined)}
              title={node.item.title}
              aria-label={node.item.title}
            >
              {node.imagePath ? <img src={mediaUrl(node.imagePath)} alt={node.item.title} loading="lazy" decoding="async" /> : <span className="thumb-fallback">No image</span>}
              <span>{node.item.title}</span>
            </button>
          )))}
        </div>
      </div>
    </section>
  );
}
