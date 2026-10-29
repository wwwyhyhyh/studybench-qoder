"""Temporary probe: natural-mode OR semantics (deleted before delivery)."""
import pylibseekdb

inst = pylibseekdb.open("/tmp/sb-nat-probe.db")
conn = inst.connect(autocommit=True)
conn.cursor().execute("CREATE DATABASE IF NOT EXISTS sb")
conn = inst.connect("sb", autocommit=True)
cur = conn.cursor()


def esc(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


cur.execute("CREATE TABLE c(id VARCHAR(32) PRIMARY KEY, body MEDIUMTEXT NOT NULL)")
cur.execute("CREATE FULLTEXT INDEX ft ON c (body) WITH PARSER NGRAM")
for rid, body in [
    ("r1", "完全二叉树的叶子结点数为 n0"),
    ("r2", "哈夫曼编码是前缀码，kruskal 按边权排序"),
    ("r3", "扭摆法测量转动惯量与摆动周期"),
    ("r4", "数据库索引与写放大"),  # 与查询无交集
]:
    cur.execute("INSERT INTO c VALUES (%s,%s)" % (esc(rid), esc(body)))
conn.commit()

cases = [
    ("kruskal 扭摆", ["r2", "r3"]),   # 跨文档 OR：A 词在 r2、B 词在 r3
    ("完全 哈夫曼", ["r1", "r2"]),     # 跨文档 OR
    ("kruskal", ["r2"]),              # ≥3 字符 ASCII 单独
    ("叶子结点", ["r1"]),              # 2-gram 连续短语
    ("生成树 转动惯量", ["r2", "r3"]),  # 3 字 CJK 跨文档
    ("索引 写放大", ["r4"]),
    ("完全不存在的词", []),            # 全部词项缺失
    ("树", []),                       # 单字 CJK（已知限制，走退路）
]
ok = True
for against, expect in cases:
    cur.execute("SELECT id FROM c WHERE MATCH(body) AGAINST (" + esc(against) + ")")
    got = sorted(row[0] for row in cur.fetchall())
    mark = "OK " if got == sorted(expect) else "DIFF"
    ok &= got == sorted(expect)
    print(f"{mark} AGAINST({against!r:20}) -> {got} (expect {sorted(expect)})")
inst.close()
print("OR-SEMANTICS:", "CONFIRMED" if ok else "CHECK ABOVE")
