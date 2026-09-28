"""肥料母液分罐奇环检测回归用例。

覆盖：
- 「偶环捷径 + 更长奇环」：BFS 着色冲突边删除后的端点普通最短路与该边
  闭合成偶环（旧实现跳过该边 -> 漏报奇环 -> 错误返回可分配），但图中
  存在更长的奇环；新实现用带奇偶状态的 BFS 必须检出。
- 三角形（最短奇环）仍正确检出；偶环（4 环）不误报。
- 多连通分量取全图最短奇环；同长按规范化肥料 ID 序列稳定决胜。
- 可分配 / 容量超额 / 0 用量不进图等既有行为不变。

直接运行：python3 test_fertilizer_split.py
"""

import fertilizer_split as fz

_failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS {name}")
    else:
        _failures.append(name)
        print(f"FAIL {name} {detail}")


def fert(rows):
    """rows: [(id, amount)] -> 肥料列表（名称无关紧要）。"""
    return [{"id": fid, "name": f"肥料{fid}", "amount": amt}
            for fid, amt in rows]


def pairs(edges):
    """edges: [(a, b)] -> 不相容关系列表（id 从 1 起）。"""
    return [{"id": i, "a_id": a, "b_id": b}
            for i, (a, b) in enumerate(edges, start=1)]


def ring_ids(result):
    return [n["id"] for n in (result["conflict_ring"] or [])]


# ------------------------------------------------------------ 核心回归用例

def test_even_shortcut_hides_longer_odd_ring():
    # 图：1-3, 1-6, 2-4, 2-5, 2-6, 3-4, 3-5
    # BFS 着色冲突边 (4,2)/(5,2) 等：删边后端点普通最短路为奇数长
    # （如 4-3-5-2，3 条边），与冲突边闭合成 4 环（偶环捷径），旧实现
    # 全部跳过 -> 漏报；但图中存在更长的 5 环 1-3-4-2-6-1。
    edges = [(1, 3), (1, 6), (2, 4), (2, 5), (2, 6), (3, 4), (3, 5)]
    r = fz.solve(2000, 2000,
                 fert([(1, 100), (2, 100), (3, 100),
                       (4, 100), (5, 100), (6, 100)]),
                 pairs(edges))
    check("偶环捷径不漏报：状态为 conflict", r["status"] == fz.CONFLICT,
          f"status={r['status']}")
    check("偶环捷径不漏报：检出 5 环 1-3-4-2-6", ring_ids(r) == [1, 3, 4, 2, 6],
          f"ring={ring_ids(r)}")
    check("偶环捷径不漏报：冲突分量为 1", r["conflict_component"] == 1,
          f"component={r['conflict_component']}")
    check("偶环捷径不漏报：conflict 时不给分罐", r["decision"] is None)
    ring_set = set(ring_ids(r))
    marked = {(e["a_id"], e["b_id"]) for e in r["edges"] if e["in_ring"]}
    expect = {(1, 3), (3, 4), (2, 4), (2, 6), (1, 6)}
    check("偶环捷径不漏报：环上 5 条边全部标记 in_ring",
          marked == expect, f"marked={marked}")
    check("偶环捷径不漏报：环上顶点都在同一分量",
          all(next(a["component"] for a in r["active"] if a["id"] == m) == 1
              for m in ring_set))


def test_triangle_still_detected():
    r = fz.solve(2000, 2000,
                 fert([(1, 800), (2, 600), (3, 700)]),
                 pairs([(1, 2), (2, 3), (1, 3)]))
    check("三角形：conflict 且环为 [1,2,3]",
          r["status"] == fz.CONFLICT and ring_ids(r) == [1, 2, 3],
          f"status={r['status']} ring={ring_ids(r)}")
    check("三角形：3 条边均标记 in_ring",
          sum(1 for e in r["edges"] if e["in_ring"]) == 3)


def test_even_cycle_no_false_positive():
    # 4 环是偶环，可二着色，不应报冲突
    r = fz.solve(2000, 2000,
                 fert([(1, 100), (2, 100), (3, 100), (4, 100)]),
                 pairs([(1, 2), (2, 3), (3, 4), (4, 1)]))
    check("4 环（偶环）：可分配", r["status"] == fz.OK, f"status={r['status']}")


def test_shortest_across_components():
    # 分量 1 为三角形（最短奇环长 3），分量 2 为 5 环；取全图最短
    r = fz.solve(2000, 2000,
                 fert([(1, 100), (2, 100), (3, 100),
                       (4, 100), (5, 100), (6, 100), (7, 100), (8, 100)]),
                 pairs([(1, 2), (2, 3), (1, 3),
                        (4, 5), (5, 6), (6, 7), (7, 8), (8, 4)]))
    check("多分量取最短：三角形胜出",
          ring_ids(r) == [1, 2, 3] and r["conflict_component"] == 1,
          f"ring={ring_ids(r)} comp={r['conflict_component']}")


def test_tie_break_canonical_ids():
    # 两个不相交三角形（同长）：规范化 ID 序列较小的 [1,2,3] 胜出
    r = fz.solve(2000, 2000,
                 fert([(1, 100), (2, 100), (3, 100),
                       (4, 100), (5, 100), (6, 100)]),
                 pairs([(1, 2), (2, 3), (1, 3),
                        (4, 5), (5, 6), (4, 6)]))
    check("同长环决胜：[1,2,3] 胜 [4,5,6]",
          ring_ids(r) == [1, 2, 3] and r["conflict_component"] == 1,
          f"ring={ring_ids(r)} comp={r['conflict_component']}")


def test_tie_break_rotated_equivalent():
    # 同一个环从不同顶点起，规范化结果必须一致（决胜稳定）
    adj = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
    got = fz._shortest_odd_ring(adj)
    check("三角形规范化为 [1,2,3]", got == [1, 2, 3], f"got={got}")


# ------------------------------------------------------------ 既有行为不变

def test_ok_chain():
    # 链 1-2-3，容量充足 -> 可分配
    r = fz.solve(2000, 2000,
                 fert([(1, 800), (2, 600), (3, 700)]),
                 pairs([(1, 2), (2, 3)]))
    check("链：可分配", r["status"] == fz.OK, f"status={r['status']}")
    check("链：decision 非空且可行",
          r["decision"] is not None and r["decision"]["chosen"]["feasible"])


def test_overflow_chain():
    # 链 1-2-3，容量不足 -> 容量超额但给出最小超额方案
    r = fz.solve(1000, 1000,
                 fert([(1, 800), (2, 600), (3, 700)]),
                 pairs([(1, 2), (2, 3)]))
    check("容量不足：overflow 且给明细",
          r["status"] == fz.OVERFLOW and r["decision"] is not None
          and r["decision"]["chosen"]["excess_total"] > 0,
          f"status={r['status']}")


def test_zero_amount_excluded():
    # 用量 0 的肥料不进图：三角形缺一条边后不再是奇环
    r = fz.solve(2000, 2000,
                 fert([(1, 800), (2, 600), (3, 0)]),
                 pairs([(1, 2), (2, 3), (1, 3)]))
    check("0 用量不进图：可分配",
          r["status"] == fz.OK and len(r["active"]) == 2,
          f"status={r['status']} active={len(r['active'])}")


def test_empty():
    r = fz.solve(2000, 2000, fert([(1, 0)]), pairs([(1, 2)]))
    check("无正用量：empty", r["status"] == fz.EMPTY, f"status={r['status']}")


def test_no_ring_marked_when_ok():
    r = fz.solve(2000, 2000,
                 fert([(1, 800), (2, 600), (3, 700)]),
                 pairs([(1, 2), (2, 3)]))
    check("可分配时无边标记 in_ring",
          all(not e["in_ring"] for e in r["edges"]))


if __name__ == "__main__":
    test_even_shortcut_hides_longer_odd_ring()
    test_triangle_still_detected()
    test_even_cycle_no_false_positive()
    test_shortest_across_components()
    test_tie_break_canonical_ids()
    test_tie_break_rotated_equivalent()
    test_ok_chain()
    test_overflow_chain()
    test_zero_amount_excluded()
    test_empty()
    test_no_ring_marked_when_ok()
    print()
    if _failures:
        print(f"{len(_failures)} 项失败：{_failures}")
        raise SystemExit(1)
    print("全部通过")
