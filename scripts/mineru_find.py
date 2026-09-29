#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 llm-for-zotero-mineru 缓存里定位文献的 MinerU 解析产物。

用法:
  python mineru_find.py                                  # 列出全部缓存及完整性
  python mineru_find.py --parent-key NESWKVII            # 按文献条目 key 找
  python mineru_find.py --attachment-key T2L3CM5H        # 按附件 key 找
  python mineru_find.py --title polyprodrug              # 按 PDF 文件名关键词找
  python mineru_find.py --parent-key NESWKVII --figures  # 命中唯一时附带图片清单
"""
import argparse
import glob
import json
import os
import sys

MINERU_CACHE = os.environ.get(
    "MINERU_CACHE", os.path.join(os.path.expanduser("~/Zotero"), "llm-for-zotero-mineru")
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def scan():
    """扫描缓存目录，返回每个目录的状态清单（新解析的排前面）。"""
    dirs = glob.glob(os.path.join(MINERU_CACHE, "*"))
    dirs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    entries = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        info = {"dir": d, "dirName": os.path.basename(d)}
        src = os.path.join(d, "_llm_source.json")
        if os.path.isfile(src):
            try:
                with open(src, encoding="utf-8") as f:
                    data = json.load(f)
                for k in ("attachmentKey", "parentItemKey", "sourceFilename", "parsedAt"):
                    info[k] = data.get(k)
            except Exception as e:
                info["error"] = str(e)
        full = os.path.join(d, "full.md")
        mani = os.path.join(d, "manifest.json")
        img_dir = os.path.join(d, "images")
        info["fullMd"] = full if os.path.isfile(full) else None
        info["manifest"] = mani if os.path.isfile(mani) else None
        info["imageCount"] = len(glob.glob(os.path.join(img_dir, "*"))) if os.path.isdir(img_dir) else 0
        if info.get("fullMd") and info.get("manifest"):
            info["status"] = "ok"
        elif info.get("fullMd") or info.get("manifest"):
            info["status"] = "incomplete"
        elif not os.path.isfile(src):
            info["status"] = "empty"
        else:
            info["status"] = "broken"
        entries.append(info)
    return entries


def match(entries, parent_key, attachment_key, title):
    out = []
    for e in entries:
        if parent_key and (e.get("parentItemKey") or "").upper() != parent_key.upper():
            continue
        if attachment_key and (e.get("attachmentKey") or "").upper() != attachment_key.upper():
            continue
        if title and title.lower() not in (e.get("sourceFilename") or "").lower():
            continue
        out.append(e)
    return out


def figures(manifest_path):
    """拍平 manifest 的 sections[].figures[]，给出 label/页码/路径/截断 caption。"""
    with open(manifest_path, encoding="utf-8") as f:
        mani = json.load(f)
    figs = []
    for sec in mani.get("sections", []):
        for fig in sec.get("figures", []):
            figs.append({
                "label": fig.get("label"),
                "page": sec.get("page"),
                "sectionPath": sec.get("path"),
                "path": fig.get("path"),
                "caption": (fig.get("caption") or "")[:300],
            })
    return figs


def main():
    ap = argparse.ArgumentParser(description="MinerU 缓存定位")
    ap.add_argument("--parent-key", dest="parent_key", help="Zotero 文献条目 key")
    ap.add_argument("--attachment-key", dest="attachment_key", help="Zotero 附件 key")
    ap.add_argument("--title", help="PDF 文件名关键词")
    ap.add_argument("--figures", action="store_true", help="命中唯一目录时输出图片清单")
    args = ap.parse_args()

    if not os.path.isdir(MINERU_CACHE):
        print(json.dumps({"error": "MinerU 缓存目录不存在: " + MINERU_CACHE}, ensure_ascii=False))
        sys.exit(1)

    entries = scan()
    if args.parent_key or args.attachment_key or args.title:
        hits = match(entries, args.parent_key, args.attachment_key, args.title)
        payload = {"matchCount": len(hits), "matches": hits}
        if args.figures:
            if len(hits) == 1 and hits[0].get("manifest"):
                payload["figures"] = figures(hits[0]["manifest"])
            elif len(hits) != 1:
                payload["figuresError"] = "匹配数不为 1，请缩小条件后再取图片清单"
            else:
                payload["figuresError"] = "该缓存缺少 manifest.json"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        ok = sum(1 for e in entries if e["status"] == "ok")
        print(json.dumps(
            {
                "ok": True,
                "cache": MINERU_CACHE,
                "total": len(entries),
                "statusOk": ok,
                "hint": "用 --parent-key/--attachment-key/--title 定位单篇，--figures 取图片清单",
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        ))


if __name__ == "__main__":
    main()
