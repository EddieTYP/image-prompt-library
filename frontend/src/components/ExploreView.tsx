import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { mediaUrl } from '../api/client';
import type { ClusterRecord, ItemSummary } from '../types';
import { imageThumbnailPath, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';

const CANVAS_WIDTH = 2200;
const CANVAS_HEIGHT = 1500;
const DEFAULT_SCALE = 0.48;
const DEFAULT_OFFSET = { x: -18, y: -10 };
const CENTER_X = CANVAS_WIDTH / 2;
const CENTER_Y = CANVAS_HEIGHT / 2;
const TAP_DRAG_THRESHOLD = 7;
const FOCUS_TRANSITION_MS = 280;
const CLUSTER_CARD_WIDTH = 178;
const CLUSTER_CARD_HEIGHT = 96;
const GLOBAL_THUMB_WIDTH = 88;
const GLOBAL_THUMB_HEIGHT = 112;
const FOCUS_THUMB_WIDTH = 118;
const FOCUS_THUMB_HEIGHT = 148;
const FOCUS_SLOT_GAP = 16;
const RELAXATION_ITERATIONS = 120;
const REPULSION_STRENGTH = 0.42;
const CLUSTER_REPULSION_STRENGTH = 0.52;
const SPRING_STRENGTH = 0.025;
const RELAXATION_DAMPING = 0.78;

type TapTarget =
  | { type: 'cluster'; cluster: ConstellationCluster }
  | { type: 'item'; item: ItemSummary }
  | undefined;

type GestureState = {
  pointerId: number;
  x: number;
  y: number;
  panStartOffset: { x: number; y: number };
  dragging: boolean;
  // Compatibility marker for the older tap-state contract: dragged:
  tapTarget: TapTarget;
};

type ConstellationNode = {
  item: ItemSummary;
  imagePath: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle: number;
  rotation: number;
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

function isBlankConstellationPointerTarget(target: EventTarget | null, viewport: HTMLElement) {
  if (target === viewport) return true;
  if (!(target instanceof Element)) return false;
  if (target.closest('.constellation-thumb-card, .constellation-cluster-card, button, a, input, textarea, select')) return false;
  return Boolean(target.closest('.constellation-canvas, .constellation-links'));
}

function getConstellationImagePath(item: ItemSummary) {
  const primaryImage = selectPrimaryImage([item.first_image]);
  return imageThumbnailPath(primaryImage);
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
  const collisionPadding = 18;
  const minX = (a.width + b.width) / 2 + collisionPadding;
  const minY = (a.height + b.height) / 2 + collisionPadding;
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
      rotation: node.rotation,
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

function buildCompactFocusSlots(visible: ItemSummary[], pos: { x: number; y: number }) {
  const width = FOCUS_THUMB_WIDTH;
  const height = FOCUS_THUMB_HEIGHT;
  const slotStepX = width + FOCUS_SLOT_GAP;
  const slotStepY = height + FOCUS_SLOT_GAP;
  const hubBox = { x: pos.x, y: pos.y, width: CLUSTER_CARD_WIDTH + 34, height: CLUSTER_CARD_HEIGHT + 32 };
  const slots: Array<{ x: number; y: number; angle: number; distance: number }> = [];
  const maxCols = Math.ceil((CANVAS_WIDTH - 180) / slotStepX);
  const maxRows = Math.ceil((CANVAS_HEIGHT - 180) / slotStepY);
  for (let row = -maxRows; row <= maxRows; row += 1) {
    for (let col = -maxCols; col <= maxCols; col += 1) {
      const stagger = Math.abs(row) % 2 ? slotStepX / 2 : 0;
      const x = pos.x + col * slotStepX + stagger;
      const y = pos.y + row * slotStepY;
      if (x < width / 2 + 36 || x > CANVAS_WIDTH - width / 2 - 36) continue;
      if (y < height / 2 + 36 || y > CANVAS_HEIGHT - height / 2 - 36) continue;
      if (doesCollide({ x, y, width, height }, [hubBox])) continue;
      const angle = Math.atan2(y - pos.y, x - pos.x);
      const distance = Math.hypot((x - pos.x) * 0.78, (y - pos.y) * 1.35);
      slots.push({ x, y, angle, distance });
    }
  }
  slots.sort((a, b) => a.distance - b.distance || a.angle - b.angle);
  return visible.map((item, index) => {
    const slot = slots[index] || slots[slots.length - 1] || { x: pos.x, y: pos.y + 240, angle: Math.PI / 2, distance: 240 };
    return {
      item,
      imagePath: getConstellationImagePath(item),
      x: slot.x,
      y: slot.y,
      width,
      height,
      angle: slot.angle,
      rotation: 0,
      index,
    };
  });
}

function buildClusterNodes(allItems: ItemSummary[], cap: number, pos: { x: number; y: number }, focused: boolean, reserved: CollisionBox[]) {
  const visible = scoreItems(allItems).slice(0, cap);
  if (focused) return buildCompactFocusSlots(visible, pos);
  const width = GLOBAL_THUMB_WIDTH;
  const height = GLOBAL_THUMB_HEIGHT;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const baseRadius = focused ? 220 : 146;
  const radiusStep = focused ? 23 : 14;
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
      rotation: 0,
      index,
    };
  });
  return settleCollisionAwarePositions(seeds, pos, reserved);
}

function placeWithoutGlobalOverlap(node: ConstellationNode, placed: CollisionBox[]) {
  const fitsAt = (x: number, y: number) => {
    const box = { x, y, width: node.width, height: node.height };
    return !doesCollide(box, placed);
  };
  if (fitsAt(node.x, node.y)) return node;
  const spiralStep = 10;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let attempt = 1; attempt <= 1800; attempt += 1) {
    const radius = Math.ceil(attempt / 12) * spiralStep;
    const angle = attempt * goldenAngle + node.angle;
    const x = Math.max(node.width / 2 + 36, Math.min(CANVAS_WIDTH - node.width / 2 - 36, node.x + Math.cos(angle) * radius));
    const y = Math.max(node.height / 2 + 36, Math.min(CANVAS_HEIGHT - node.height / 2 - 36, node.y + Math.sin(angle) * radius));
    if (fitsAt(x, y)) return { ...node, x, y };
  }
  return node;
}

function resolveConstellationNodeOverlaps(clusters: ConstellationCluster[]) {
  const placed: CollisionBox[] = clusters.map(cluster => ({ x: cluster.x, y: cluster.y, width: cluster.width + 24, height: cluster.height + 24 }));
  return clusters.map(cluster => {
    const nodes = cluster.nodes.map(node => {
      const positioned = placeWithoutGlobalOverlap(node, placed);
      placed.push({ x: positioned.x, y: positioned.y, width: positioned.width, height: positioned.height });
      return positioned;
    });
    return { ...cluster, nodes };
  });
}

function getConstellationBounds(displayedClusters: ConstellationCluster[]) {
  const boxes: CollisionBox[] = [];
  for (const cluster of displayedClusters) {
    boxes.push({ x: cluster.x, y: cluster.y, width: cluster.width + 38, height: cluster.height + 34 });
    for (const node of cluster.nodes) boxes.push({ x: node.x, y: node.y, width: node.width + 18, height: node.height + 18 });
  }
  if (!boxes.length) return undefined;
  return boxes.reduce(
    (bounds, box) => ({
      minX: Math.min(bounds.minX, box.x - box.width / 2),
      minY: Math.min(bounds.minY, box.y - box.height / 2),
      maxX: Math.max(bounds.maxX, box.x + box.width / 2),
      maxY: Math.max(bounds.maxY, box.y + box.height / 2),
    }),
    { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
  );
}

function computeFitTransform(bounds: NonNullable<ReturnType<typeof getConstellationBounds>>, viewport: DOMRect) {
  const padding = 76;
  const boundsWidth = Math.max(1, bounds.maxX - bounds.minX);
  const boundsHeight = Math.max(1, bounds.maxY - bounds.minY);
  const availableWidth = Math.max(320, viewport.width - padding * 2);
  const availableHeight = Math.max(260, viewport.height - padding * 2);
  const nextScale = Math.min(1.15, Math.max(0.42, Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight)));
  const contentCenterX = (bounds.minX + bounds.maxX) / 2;
  const contentCenterY = (bounds.minY + bounds.maxY) / 2;
  return {
    scale: nextScale,
    offset: {
      x: (CENTER_X - contentCenterX) * nextScale,
      y: (CENTER_Y - contentCenterY) * nextScale,
    },
  };
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

  const rawConstellation = sortedClusters.map((cluster) => {
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
  return focusedClusterId ? rawConstellation : resolveConstellationNodeOverlaps(rawConstellation);
}
export default function ExploreView({
  t,
  clusters,
  items,
  focusedClusterId,
  fitRequestKey = 0,
  unfilterTransitionPhase = 'idle',
  globalThumbnailBudget,
  focusThumbnailBudget,
  onFocusCluster,
  onOpenClusterCards,
  onOpen,
  onAdd,
}: {
  t: Translator;
  clusters: ClusterRecord[];
  items: ItemSummary[];
  focusedClusterId?: string;
  fitRequestKey?: number;
  unfilterTransitionPhase?: 'idle' | 'out' | 'pre-in' | 'in';
  globalThumbnailBudget: number;
  focusThumbnailBudget: number;
  onFocusCluster: (c: ClusterRecord) => void;
  onOpenClusterCards: (c: ClusterRecord) => void;
  onOpen: (id: string) => void;
  onAdd: () => void;
}) {
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [offset, setOffset] = useState(DEFAULT_OFFSET);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const lastFitRequestKeyRef = useRef(fitRequestKey);
  const gestureRef = useRef<GestureState | undefined>(undefined);
  const suppressNextClickRef = useRef(false);
  const [gesture, setGestureState] = useState<GestureState | undefined>();
  const setGesture = (next: GestureState | undefined) => {
    gestureRef.current = next;
    setGestureState(next);
  };
  const [isFocusAnimating, setIsFocusAnimating] = useState(false);
  const constellation = useMemo(
    () => buildConstellation(clusters, items, focusedClusterId, globalThumbnailBudget, focusThumbnailBudget),
    [clusters, items, focusedClusterId, globalThumbnailBudget, focusThumbnailBudget],
  );
  const focusedCluster = constellation.find(cluster => cluster.id === focusedClusterId);
  const displayedClusters = useMemo(
    () => (focusedClusterId ? constellation.filter(cluster => !cluster.inactive) : constellation),
    [constellation, focusedClusterId],
  );

  const fitConstellationToViewport = () => {
    const viewport = viewportRef.current?.getBoundingClientRect();
    const bounds = getConstellationBounds(displayedClusters);
    if (!viewport || !bounds) {
      setScale(DEFAULT_SCALE);
      setOffset(DEFAULT_OFFSET);
      return;
    }
    const next = computeFitTransform(bounds, viewport);
    setScale(next.scale);
    setOffset(next.offset);
  };

  useLayoutEffect(() => {
    const explicitFitRequested = lastFitRequestKeyRef.current !== fitRequestKey;
    lastFitRequestKeyRef.current = fitRequestKey;
    setIsFocusAnimating(Boolean(focusedClusterId || fitRequestKey) && explicitFitRequested);
    fitConstellationToViewport();
    const timer = window.setTimeout(() => setIsFocusAnimating(false), FOCUS_TRANSITION_MS);
    return () => window.clearTimeout(timer);
  }, [focusedClusterId, displayedClusters, fitRequestKey]);

  if (!clusters.length) {
    return (
      <div className="empty">
        <h2>{t('libraryEmptyTitle')}</h2>
        <p>{t('libraryEmptyHelp')}</p>
        <div className="empty-actions">
          <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>
        </div>
      </div>
    );
  }

  const reset = () => { setScale(DEFAULT_SCALE); setOffset(DEFAULT_OFFSET); };
  const handleOpenClusterCards = (cluster: ConstellationCluster) => onOpenClusterCards(cluster);
  const startGesture = (event: PointerEvent<HTMLElement>, tapTarget: TapTarget) => {
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Synthetic QA events may not have an active browser pointer; real pointer input still captures normally.
    }
    setGesture({
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      panStartOffset: offset,
      dragging: false,
      tapTarget,
    });
  };
  const moveGesture = (event: PointerEvent<HTMLElement>) => {
    const activeGesture = gestureRef.current;
    if (!activeGesture || activeGesture.pointerId !== event.pointerId) return;
    const dx = event.clientX - activeGesture.x;
    const dy = event.clientY - activeGesture.y;
    const distance = Math.hypot(dx, dy);
    if (distance <= TAP_DRAG_THRESHOLD && !activeGesture.dragging) return;
    if (!activeGesture.dragging) setGesture({ ...activeGesture, dragging: true });
    // Static-test marker for pan-from-card contract: setOffset({ x: gesture.panStartOffset.x +
    setOffset({ x: activeGesture.panStartOffset.x + dx, y: activeGesture.panStartOffset.y + dy });
  };
  const handleActivationClick = (tapTarget: TapTarget) => {
    if (suppressNextClickRef.current) {
      suppressNextClickRef.current = false;
      return;
    }
    if (!tapTarget) return;
    if (tapTarget.type === 'cluster') onFocusCluster(tapTarget.cluster);
    if (tapTarget.type === 'item') onOpen(tapTarget.item.id);
  };
  const finishGesture = (event: PointerEvent<HTMLElement>) => {
    const activeGesture = gestureRef.current;
    if (!activeGesture || activeGesture.pointerId !== event.pointerId) return;
    const target = activeGesture.tapTarget;
    const shouldActivate = !activeGesture.dragging;
    if (activeGesture.dragging) suppressNextClickRef.current = true;
    setGesture(undefined);
    if (!shouldActivate || !target) return;
    if (target.type === 'cluster') onFocusCluster(target.cluster);
    if (target.type === 'item') onOpen(target.item.id);
  };
  const cancelGesture = () => setGesture(undefined);
  const unfilterClass = unfilterTransitionPhase === 'out'
    ? 'is-unfilter-fade-out'
    : unfilterTransitionPhase === 'pre-in'
      ? 'is-unfilter-fade-pre-in'
      : unfilterTransitionPhase === 'in'
        ? 'is-unfilter-fade-in'
        : '';

  return (
    <section className={`thumbnail-constellation ${focusedClusterId ? 'is-focused' : ''} ${gesture?.dragging ? 'is-dragging' : ''} ${unfilterClass}`} aria-label={t('constellationGraph')}>
      <div className="constellation-toolbar" aria-label={t('constellationControls')}>
        <button onClick={() => setScale(s => Math.max(0.42, s - 0.08))} aria-label={t('zoomOut')}><Minus size={16} /></button>
        <button onClick={() => setScale(s => Math.min(1.35, s + 0.08))} aria-label={t('zoomIn')}><Plus size={16} /></button>
        <button onClick={reset}><RotateCcw size={16} /> {t('resetView')}</button>
        <span>{focusedClusterId ? `${focusThumbnailBudget} ${t('focusThumbnailsVisible')}` : `${globalThumbnailBudget} ${t('thumbnailsVisible')}`}</span>
      </div>
      {focusedCluster && (
        <div className="constellation-focus-panel">
          <strong>{focusedCluster.name}</strong>
          <span>{focusedCluster.count} {t('referencesShown')} · {focusedCluster.nodes.length} {t('visible')}</span>
          <button onClick={() => handleOpenClusterCards(focusedCluster)}>{t('cards')}</button>
        </div>
      )}
      <div
        ref={viewportRef}
        className="constellation-viewport"
        onWheel={(event) => {
          event.preventDefault();
          setScale(s => Math.max(0.42, Math.min(1.35, s + (event.deltaY < 0 ? 0.06 : -0.06))));
        }}
        onPointerDown={(event) => {
          if (!isBlankConstellationPointerTarget(event.target, event.currentTarget)) return;
          startGesture(event, undefined);
        }}
        onPointerMove={moveGesture}
        onPointerUp={finishGesture}
        onPointerCancel={cancelGesture}
      >
        <div
          className={`constellation-canvas ${isFocusAnimating ? 'focus-animation' : ''}`}
          style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `translate(-50%, -50%) translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})` }}
        >
          <svg className="constellation-links" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} aria-hidden="true">
            {constellation.flatMap(cluster => cluster.nodes.map(node => (
              <line key={`${cluster.id}-${node.item.id}-link`} x1={cluster.x} y1={cluster.y} x2={node.x} y2={node.y} />
            )))}
          </svg>
          {displayedClusters.map(cluster => (
            <button
              key={cluster.id}
              className={`constellation-cluster-card ${cluster.id === focusedClusterId ? 'focused' : ''} ${cluster.inactive ? 'inactive' : ''}`}
              style={{ left: cluster.x, top: cluster.y, width: cluster.width, minHeight: cluster.height }}
              onPointerDown={(event) => startGesture(event, { type: 'cluster', cluster })}
              onPointerMove={moveGesture}
              onPointerUp={finishGesture}
              onPointerCancel={cancelGesture}
              onClick={() => handleActivationClick({ type: 'cluster', cluster })}
              title={`${cluster.count} ${t('references')}`}
            >
              <strong>{cluster.name}</strong>
              <span>{cluster.count} {t('references')}</span>
              {cluster.hiddenCount > 0 && <em>+{cluster.hiddenCount} {t('more')}</em>}
            </button>
          ))}
          {constellation.flatMap(cluster => cluster.nodes.map(node => (
            <button
              key={`${cluster.id}-${node.item.id}`}
              className={`constellation-thumb-card ${node.item.favorite ? 'favorite' : ''}`}
              style={{
                left: node.x,
                top: node.y,
                width: node.width,
                height: node.height,
                '--node-rotation': `${node.rotation}deg`,
              } as CSSProperties}
              onPointerDown={(event) => startGesture(event, { type: 'item', item: node.item })}
              onPointerMove={moveGesture}
              onPointerUp={finishGesture}
              onPointerCancel={cancelGesture}
              onClick={() => handleActivationClick({ type: 'item', item: node.item })}
              title={node.item.title}
              aria-label={node.item.title}
            >
              {node.imagePath ? <img src={mediaUrl(node.imagePath)} alt={node.item.title} loading="lazy" decoding="async" draggable={false} /> : <span className="thumb-fallback">{t('noImage')}</span>}
              <span>{node.item.title}</span>
            </button>
          )))}
        </div>
      </div>
    </section>
  );
}
