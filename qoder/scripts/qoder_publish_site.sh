#!/usr/bin/env bash
# 把 qoder/site/dist 发布到 Qoder Sites，并设为「任何人都可访问」。
#
# ⚠ 这是**对外发布**动作：站点一旦公开，链接即可能被转发/收录。脚本默认只做检查，
#    必须显式加 --yes 才会真正发布。
#
# 用法：
#   export QODER_PERSONAL_ACCESS_TOKEN="<PAT>"        # 或在 Qoder 里交互登录过
#   bash qoder/scripts/qoder_publish_site.sh            # 干跑：检查登录 + 打印将上报的内容
#   bash qoder/scripts/qoder_publish_site.sh --yes      # 真发布并设公开
#
# 回退：发布失败不要重复换 actionId；用同一 actionId 重试（官方恢复语义）。
set -uo pipefail
PROJECT_ROOT="E:/CodeX/PowerContext-2026"
WEB_DIR="qoder/site/dist"
DISPLAY_NAME="学研台 StudyBench"
SLUG="studybench"
YES=0; [ "${1:-}" = "--yes" ] && YES=1

uuid() { python -c "import uuid;print(uuid.uuid4())"; }
jget() { python -c "
import sys,json
d=json.load(sys.stdin)
for k in sys.argv[1].split('.'):
    if isinstance(d,list): d=d[int(k)]
    else: d=d.get(k) if isinstance(d,dict) else None
print('' if d is None else d)
" "$1" 2>/dev/null; }

cd "$PROJECT_ROOT" || { echo "找不到仓库 $PROJECT_ROOT"; exit 1; }

echo "== 1/5 登录态 =="
AUTH=$(qoder sites list 2>&1); echo "$AUTH" | head -c 400; echo
[ "$(printf '%s' "$AUTH" | jget ok)" = "True" ] || { echo "✗ 未登录。先 export QODER_PERSONAL_ACCESS_TOKEN=... 或运行 qoder 后 /login"; exit 3; }

echo "== 2/5 产物自检 =="
for f in index.html styles.css app.js data/index_export.json; do
  [ -f "$WEB_DIR/$f" ] || { echo "✗ 缺 $WEB_DIR/$f"; exit 2; }
done
python - "$WEB_DIR/data/index_export.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
m=d["meta"]; print(f"  索引：{m['n_docs']} 篇 / {m['n_chunks']} 块 / 平均 {m['avg_len']} 字符")
assert m["corpus"]=="demo", "导出的是非 demo 语料，检查是否误把个人工作区发上网"
print("  语料来源：demo（已脱敏）✓")
PY
[ -z "$(grep -o '<!-- LOGS:REPLACE -->' "$WEB_DIR/index.html")" ] || echo "  ⚠ 站点里还有 LOGS:REPLACE 占位未注入"
[ -z "$(grep -o '<!-- REPO:REPLACE -->' "$WEB_DIR/index.html")" ] || echo "  ⚠ 站点里还有 REPO:REPLACE 占位未注入"

ACTION=$(uuid)
echo "== 3/5 打包草稿（actionId=$ACTION）=="
PREP_INPUT=$(python -c "
import json,sys
print(json.dumps({
  'actionId': sys.argv[1], 'projectRoot': sys.argv[2], 'webDirectory': sys.argv[3],
  'displayName': sys.argv[4], 'slug': sys.argv[5], 'spa': False, 'databaseAccess': 'none',
}, ensure_ascii=False))" "$ACTION" "$PROJECT_ROOT" "$WEB_DIR" "$DISPLAY_NAME" "$SLUG")
echo "$PREP_INPUT"
if [ "$YES" != 1 ]; then echo; echo "干跑结束。确认无误后加 --yes 真发布。"; exit 0; fi

qoder sites prepare_site --input "$PREP_INPUT" | tee /tmp/sb_prepare.json | head -c 800; echo
# prepare_site 的返回结构：result.siteId / result.projectId（不是 result.site.id）
SITE_ID=$(jget result.siteId < /tmp/sb_prepare.json)
echo "  siteId=${SITE_ID:-（未返回，稍后从 list_sites 取）}"

echo "== 4/5 等草稿就绪 =="
for i in $(seq 1 40); do
  ST=$(qoder sites get_publish_status --input "{\"actionId\":\"$ACTION\"}")
  READY=$(printf '%s' "$ST" | jget result.artifactReady)
  DS=$(printf '%s' "$ST" | jget result.descriptorStatus)
  echo "  [$i] artifactReady=$READY descriptorStatus=$DS"
  [ "$READY" = "True" ] && break
  sleep 5
done

echo "== 5/5 发布 + 设公开 =="
qoder sites publish_site --input "{\"actionId\":\"$ACTION\"}" | tee /tmp/sb_publish.json | head -c 800; echo

if [ -z "${SITE_ID:-}" ]; then
  # list_sites 的结构：result.projects[].site.site_id（display_name 在项目层）
  SITE_ID=$(qoder sites list | python -c "
import sys,json
d=json.load(sys.stdin)
for p in (d.get('result') or {}).get('projects') or []:
    if p.get('display_name')=='$DISPLAY_NAME':
        print(((p.get('site') or {}).get('site_id')) or ''); break
")
fi
echo "  siteId=$SITE_ID"
if [ -n "$SITE_ID" ]; then
  ACC=$(qoder sites get_site_access --input "{\"siteId\":\"$SITE_ID\"}")
  ACCESS_REF=$(printf '%s' "$ACC" | jget result.accessRef)
  echo "  当前可见性：$(printf '%s' "$ACC" | jget result.policy.mode)"
  if [ -n "$ACCESS_REF" ]; then
    qoder sites update_access_policy --input "$(python -c "
import json,sys,uuid
print(json.dumps({'siteId':sys.argv[1],'requestId':str(uuid.uuid4()),'accessRef':sys.argv[2],'mode':'public','confirmPublic':True}))" "$SITE_ID" "$ACCESS_REF")" | head -c 600; echo
    echo "  ✓ 已设为「任何人都可访问」"
  else
    echo "  ⚠ 未取到 accessRef，请到 Qoder 站点面板手动改可见性为「任何人都可访问」"
  fi
  HOST=$(qoder sites get_site --input "{\"siteId\":\"$SITE_ID\"}" | python -c "
import sys,json
d=json.load(sys.stdin)['result']
print(((d.get('site') or {}).get('host')) or '')")
  [ -n "$HOST" ] && echo "  站点地址：https://$HOST/"
fi
echo
echo "完成。用**无痕窗口**打开站点链接核对（未登录也能看）。站点编辑后再发布一次才会生效。"
