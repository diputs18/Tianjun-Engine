function top(box) { return { x: box.x, y: box.top }; }
function bottom(box) { return { x: box.x, y: box.bottom }; }
function left(box) { return { x: box.left, y: box.y }; }
function right(box) { return { x: box.right, y: box.y }; }

function elementBox(element, stageRect) {
  const rect = element.getBoundingClientRect();
  return {
    left: rect.left - stageRect.left,
    right: rect.right - stageRect.left,
    top: rect.top - stageRect.top,
    bottom: rect.bottom - stageRect.top,
    x: rect.left - stageRect.left + rect.width / 2,
    y: rect.top - stageRect.top + rect.height / 2,
  };
}

function smartAnchor(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? right(from) : left(from);
  return dy > 0 ? bottom(from) : top(from);
}

function labelPoint(item, start, end, lane) {
  if (item.labelAnchor === "left") return { x: start.x - 62, y: (start.y + end.y) / 2 };
  if (item.labelAnchor === "right") return { x: lane + 28, y: (start.y + end.y) / 2 };
  if (item.labelAnchor === "below") return { x: (start.x + end.x) / 2, y: start.y + 42 };
  return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
}

export function measuredPath(item, sourceElement, targetElement, stageRect) {
  const source = elementBox(sourceElement, stageRect);
  const target = elementBox(targetElement, stageRect);
  const pair = `${item.source}-${item.target}`;
  const reversePair = `${item.target}-${item.source}`;
  const verticalPairs = new Set([
    "border1-pe1", "pe1-dc1", "border2-pe2", "pe2-dc2", "border3-pe3", "pe3-dc3",
  ]);
  const horizontalPairs = new Set(["pe1-pe2", "pe2-pe3"]);
  const accessPairs = new Set([
    "user-access-border1", "user-access-border2", "user-access-border3",
  ]);

  if (accessPairs.has(pair) || accessPairs.has(reversePair)) {
    const sourceIsAccess = item.source === "user-access";
    const accessBox = sourceIsAccess ? source : target;
    const borderBox = sourceIsAccess ? target : source;
    const start = bottom(accessBox);
    const end = top(borderBox);
    const midY = start.y + Math.max(20, (end.y - start.y) * 0.48);
    return {
      path: `M ${start.x} ${start.y} C ${start.x} ${midY}, ${end.x} ${midY}, ${end.x} ${end.y}`,
      label: { x: (start.x + end.x) / 2, y: midY - 10 },
    };
  }

  if (verticalPairs.has(pair) || verticalPairs.has(reversePair)) {
    const sourceAboveTarget = source.y <= target.y;
    const start = sourceAboveTarget ? bottom(source) : top(source);
    const end = sourceAboveTarget ? top(target) : bottom(target);
    return {
      path: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
      label: labelPoint(item, start, end, start.x),
    };
  }

  if (horizontalPairs.has(pair) || horizontalPairs.has(reversePair)) {
    const sourceLeftOfTarget = source.x < target.x;
    const start = sourceLeftOfTarget ? right(source) : left(source);
    const end = sourceLeftOfTarget ? left(target) : right(target);
    return {
      path: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
      label: { x: (start.x + end.x) / 2, y: start.y + 42 },
    };
  }

  const start = smartAnchor(source, target);
  const end = smartAnchor(target, source);
  const midX = (start.x + end.x) / 2;
  const bendY = item.type.includes("access")
    ? Math.min(start.y, end.y) + 70
    : (start.y + end.y) / 2;
  const path = item.type.includes("branch")
    ? `M ${start.x} ${start.y} C ${midX + 40} ${start.y}, ${midX + 40} ${end.y}, ${end.x} ${end.y}`
    : `M ${start.x} ${start.y} C ${midX} ${bendY}, ${midX} ${bendY}, ${end.x} ${end.y}`;
  return {
    path,
    label: {
      x: (start.x + end.x) / 2 + (item.labelAnchor === "right" ? 48 : 0),
      y: (start.y + end.y) / 2 - 16,
    },
  };
}
