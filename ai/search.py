"""
ai/search.py
============
Real, executing search algorithms (BFS, DFS, A*) that decide the AI's
next target cell. These are not decorative -- ai.agent.SearchAgent calls
straight into these functions every turn, so whichever algorithm is
selected genuinely drives the AI's targeting behavior.

Problem formulation
--------------------
The board is treated as an undirected grid graph: each cell (r, c) is a
node, connected to its 4 orthogonal neighbors. A search starts from the
cell(s) most relevant to the current knowledge state:

    - If any of the opponent's ships is currently HIT but not yet SUNK,
      those hit cells are the start nodes ("hunt mode": search outward
      from a wound to find the rest of the ship).
    - Otherwise, the single start node is the board's center cell
      ("sweep mode": no leads yet, so begin from the most central,
      highest-coverage point on the board).

The goal test is the same for all three algorithms: the first UNKNOWN
(never-fired-upon) cell the search reaches. What differs is the ORDER
in which each algorithm reaches it:

    BFS   -- explores level by level (a FIFO queue), so it always finds
             the closest untried cell by number of grid steps.
    DFS   -- dives along one direction as far as possible (a LIFO
             stack) before backtracking, so it can reach a much farther
             cell first even though a closer one exists.
    A*    -- orders cells by f(n) = g(n) + h(n) (a priority queue), so
             it reaches a close AND promising cell efficiently.

g(n), h(n), f(n) for A*
------------------------
    g(n) = number of grid steps already taken from the nearest start
           node to n (uniform edge cost of 1 per step -- this is exact,
           not estimated, since it's accumulated during the search).
    h(n) = Manhattan distance from n to the nearest active hit cell, or
           to the board center if there are no active hits. This is an
           admissible, battleship-appropriate heuristic: it never
           overestimates the number of orthogonal steps to the region
           of the board most likely to contain the rest of a wounded
           ship (or, with no leads, the statistically richest area).
    f(n) = g(n) + h(n) -- the priority A* pops nodes in.

Every function below returns a fully-populated result dict (see
_finalize()) with the metrics and full step-by-step trace the frontend
needs to animate: nodes explored, states visited, wall-clock search
time, search depth, the chosen target, and per-step frontier/current/
explored snapshots for the tactical visualization.
"""

import heapq
import itertools
import time
from collections import deque

from ai.probability import UNKNOWN, MISS, HIT, SUNK

# 4-directional neighbor offsets, in a fixed deterministic order.
_DIRECTIONS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


def _neighbors(r, c, size):
    for dr, dc in _DIRECTIONS:
        nr, nc = r + dr, c + dc
        if 0 <= nr < size and 0 <= nc < size:
            yield (nr, nc)


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _active_hits(tracking_grid, size):
    """Cells that are HIT but not yet resolved into a SUNK ship."""
    return [
        (r, c)
        for r in range(size)
        for c in range(size)
        if tracking_grid[r][c] == HIT
    ]


def _start_nodes(tracking_grid, size):
    """Multi-source starting points: active hits, or the board center."""
    hits = sorted(_active_hits(tracking_grid, size))
    if hits:
        return hits
    center = (size // 2, size // 2)
    return [center]


def _heuristic(cell, active_hits, size):
    """h(n): Manhattan distance to the nearest lead (hit, or center)."""
    if active_hits:
        return min(_manhattan(cell, h) for h in active_hits)
    center = (size // 2, size // 2)
    return _manhattan(cell, center)


def _is_goal(tracking_grid, cell):
    r, c = cell
    return tracking_grid[r][c] == UNKNOWN


def _fallback_target(tracking_grid, size):
    """Should only trigger if literally every cell has been fired upon."""
    for r in range(size):
        for c in range(size):
            if tracking_grid[r][c] == UNKNOWN:
                return (r, c)
    return (0, 0)


def _path_depth(parent, target):
    depth = 0
    node = target
    while parent.get(node) is not None:
        node = parent[node]
        depth += 1
    return depth


def _finalize(algorithm, target, nodes_explored, visited_count, steps, depth,
              start_time, extra=None):
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    result = {
        "algorithm": algorithm,
        "target": list(target),
        "nodes_explored": nodes_explored,
        "states_visited": visited_count,
        "search_time_ms": round(elapsed_ms, 4),
        "search_depth": depth,
        "steps": steps,
    }
    if extra:
        result.update(extra)
    return result


# ---------------------------------------------------------------------
# Breadth-First Search
# ---------------------------------------------------------------------
def bfs_search(tracking_grid, board_size=10):
    """
    Explore the grid level-by-level from the start node(s) with a FIFO
    queue. Guarantees the returned target is the closest (in grid
    steps) untried cell to a lead.
    """
    start_time = time.perf_counter()
    size = board_size
    starts = _start_nodes(tracking_grid, size)

    visited = set(starts)
    parent = {s: None for s in starts}
    queue = deque(starts)

    steps = []
    nodes_explored = 0
    target = None

    while queue:
        frontier_snapshot = list(queue)
        current = queue.popleft()
        nodes_explored += 1
        steps.append({
            "frontier": [list(x) for x in frontier_snapshot],
            "current": list(current),
            "explored": [list(x) for x in visited],
        })

        if _is_goal(tracking_grid, current):
            target = current
            break

        for nb in _neighbors(current[0], current[1], size):
            if nb not in visited:
                visited.add(nb)
                parent[nb] = current
                queue.append(nb)

    if target is None:
        target = _fallback_target(tracking_grid, size)

    depth = _path_depth(parent, target)
    return _finalize("BFS", target, nodes_explored, len(visited), steps, depth, start_time)


# ---------------------------------------------------------------------
# Depth-First Search
# ---------------------------------------------------------------------
def dfs_search(tracking_grid, board_size=10):
    """
    Explore the grid depth-first using an explicit stack (no recursion,
    so arbitrarily deep boards never risk a stack overflow). Dives along
    one fixed direction order as far as possible before backtracking,
    so it commonly reaches a farther cell than BFS would before finding
    an untried one.
    """
    start_time = time.perf_counter()
    size = board_size
    starts = _start_nodes(tracking_grid, size)

    visited = set()
    parent = {}
    stack = list(reversed(starts))  # pop() takes the last -> first start explored first

    steps = []
    nodes_explored = 0
    target = None

    while stack:
        frontier_snapshot = list(stack)
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current not in parent:
            parent[current] = None
        nodes_explored += 1
        steps.append({
            "frontier": [list(x) for x in frontier_snapshot],
            "current": list(current),
            "explored": [list(x) for x in visited],
        })

        if _is_goal(tracking_grid, current):
            target = current
            break

        # push neighbors in reverse fixed order so the first-priority
        # direction ends up on top of the stack (explored first)
        for nb in reversed(list(_neighbors(current[0], current[1], size))):
            if nb not in visited:
                stack.append(nb)
                if nb not in parent:
                    parent[nb] = current

    if target is None:
        target = _fallback_target(tracking_grid, size)

    depth = _path_depth(parent, target)
    return _finalize("DFS", target, nodes_explored, len(visited), steps, depth, start_time)


# ---------------------------------------------------------------------
# A* Search
# ---------------------------------------------------------------------
def a_star_search(tracking_grid, board_size=10):
    """
    Priority-queue search ordered by f(n) = g(n) + h(n). See the module
    docstring for exactly how g, h, and f are defined for this problem.
    """
    start_time = time.perf_counter()
    size = board_size
    starts = _start_nodes(tracking_grid, size)
    active_hits = _active_hits(tracking_grid, size)

    counter = itertools.count()
    g_score = {s: 0 for s in starts}
    parent = {s: None for s in starts}
    open_members = set(starts)
    open_heap = []
    for s in starts:
        f = g_score[s] + _heuristic(s, active_hits, size)
        heapq.heappush(open_heap, (f, next(counter), s))

    closed = set()
    steps = []
    nodes_explored = 0
    target = None
    target_f = target_g = target_h = None

    while open_heap:
        f, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        open_members.discard(current)
        nodes_explored += 1
        steps.append({
            "frontier": [list(x) for x in open_members],
            "current": list(current),
            "explored": [list(x) for x in closed],
        })

        if _is_goal(tracking_grid, current):
            target = current
            target_g = g_score[current]
            target_h = _heuristic(current, active_hits, size)
            target_f = target_g + target_h
            break

        for nb in _neighbors(current[0], current[1], size):
            if nb in closed:
                continue
            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(nb, float("inf")):
                g_score[nb] = tentative_g
                parent[nb] = current
                f_nb = tentative_g + _heuristic(nb, active_hits, size)
                heapq.heappush(open_heap, (f_nb, next(counter), nb))
                open_members.add(nb)

    if target is None:
        target = _fallback_target(tracking_grid, size)
        target_g = g_score.get(target, _path_depth(parent, target))
        target_h = _heuristic(target, active_hits, size)
        target_f = target_g + target_h

    depth = target_g if target_g is not None else _path_depth(parent, target)
    extra = {"g_target": target_g, "h_target": target_h, "f_target": target_f}
    return _finalize("A*", target, nodes_explored, len(closed), steps, depth, start_time, extra)


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------
_ALGORITHMS = {
    "bfs": bfs_search,
    "dfs": dfs_search,
    "astar": a_star_search,
    "a_star": a_star_search,
    "a*": a_star_search,
}


def run_search(algorithm, tracking_grid, board_size=10):
    """Look up and execute a search algorithm by short string id."""
    fn = _ALGORITHMS.get(algorithm.lower().replace(" ", ""), bfs_search)
    return fn(tracking_grid, board_size)
