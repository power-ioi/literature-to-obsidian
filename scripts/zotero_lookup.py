#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zotero 本地库只读查询（不打断 Zotero 运行，绝不写库）。

用法:
  python zotero_lookup.py                     # 环境自检：库是否可读、条目/标注总数
  python zotero_lookup.py --title 关键词      # 按标题模糊搜索
  python zotero_lookup.py --title 关键词 --author Liu --year 2026
  python zotero_lookup.py --key NESWKVII      # 按 item key 精确取条目

输出 JSON：元数据、顶层附件（key / storage 路径 / MinerU 缓存）、标注、子笔记。
"""
import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time

ZOTERO_HOME = os.environ.get("ZOTERO_HOME", os.path.expanduser("~/Zotero"))
ZOTERO_DB = os.environ.get("ZOTERO_DB", os.path.join(ZOTERO_HOME, "zotero.sqlite"))
ZOTERO_STORAGE = os.path.join(ZOTERO_HOME, "storage")
MINERU_CACHE = os.environ.get(
    "MINERU_CACHE", os.path.join(ZOTERO_HOME, "llm-for-zotero-mineru")
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


SNAPSHOT_DIR = os.path.join(tempfile.gettempdir(), "zotero_ro_snapshot")


def make_snapshot():
    """把 zotero.sqlite(+wal) 复制为临时快照再读。

    Zotero 运行中持有 WAL，直接只读连接会报 database is locked；
    快照方式完全不触碰原库，且数据与最近一次提交一致。
    """
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    dst = os.path.join(SNAPSHOT_DIR, "zotero.sqlite")
    dst_wal = dst + "-wal"
    last_err = None
    for _ in range(3):
        try:
            shutil.copy2(ZOTERO_DB, dst)
            wal = ZOTERO_DB + "-wal"
            if os.path.isfile(wal):
                shutil.copy2(wal, dst_wal)
            elif os.path.isfile(dst_wal):
                os.remove(dst_wal)
            return dst
        except OSError as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError("无法复制 Zotero 数据库快照（Zotero 可能正在写入）: " + str(last_err))


def open_db():
    # 打开临时快照（非只读 URI，让 SQLite 在副本上完成 WAL 恢复），原库零接触
    dst = make_snapshot()
    con = sqlite3.connect(dst)
    con.row_factory = sqlite3.Row
    return con


def mineru_lookup(parent_key, attachment_key):
    """在 MinerU 缓存中按条目 key / 附件 key 找解析目录，返回目录路径或 None。"""
    for src in glob.glob(os.path.join(MINERU_CACHE, "*", "_llm_source.json")):
        try:
            with open(src, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("parentItemKey") == parent_key or data.get("attachmentKey") == attachment_key:
            return os.path.dirname(src)
    return None


def item_fields(con, item_id):
    rows = con.execute(
        "SELECT f.fieldName AS name, idv.value AS value"
        " FROM itemData id JOIN fields f ON f.fieldID = id.fieldID"
        " JOIN itemDataValues idv ON idv.valueID = id.valueID"
        " WHERE id.itemID = ?",
        (item_id,),
    ).fetchall()
    return {r["name"]: r["value"] for r in rows}


def item_creators(con, item_id):
    rows = con.execute(
        "SELECT c.firstName AS first, c.lastName AS last, ic.orderIndex AS idx"
        " FROM itemCreators ic JOIN creators c ON c.creatorID = ic.creatorID"
        " WHERE ic.itemID = ? ORDER BY ic.orderIndex",
        (item_id,),
    ).fetchall()
    return [(r["first"] or "").strip() + " " + (r["last"] or "").strip() for r in rows]


def item_attachments(con, parent_item_id, parent_key):
    rows = con.execute(
        "SELECT i.itemID AS itemID, i.key AS key, ia.path AS path, ia.contentType AS ctype"
        " FROM itemAttachments ia JOIN items i ON i.itemID = ia.itemID"
        " WHERE ia.parentItemID = ?"
        "   AND i.itemID NOT IN (SELECT itemID FROM deletedItems)",
        (parent_item_id,),
    ).fetchall()
    atts = []
    for r in rows:
        att = {"itemID": r["itemID"], "key": r["key"], "contentType": r["ctype"], "path": r["path"]}
        p = r["path"] or ""
        if p.startswith("storage:"):
            full = os.path.join(ZOTERO_STORAGE, r["key"], p[len("storage:"):])
            att["storagePath"] = full
            att["exists"] = os.path.isfile(full)
        if (r["ctype"] or "").lower().find("pdf") >= 0:
            att["mineruCache"] = mineru_lookup(parent_key, r["key"])
        atts.append(att)
    return atts


def item_annotations(con, attachment_item_ids):
    if not attachment_item_ids:
        return []
    q = (
        "SELECT i.key AS annoKey, ia.parentItemID AS attID, ia.type AS type,"
        " ia.text AS text, ia.comment AS comment"
        " FROM itemAnnotations ia JOIN items i ON i.itemID = ia.itemID"
        " WHERE ia.parentItemID IN (" + ",".join("?" * len(attachment_item_ids)) + ")"
        " ORDER BY i.itemID"
    )
    rows = con.execute(q, attachment_item_ids).fetchall()
    return [
        {"key": r["annoKey"], "type": r["type"], "text": r["text"], "comment": r["comment"]}
        for r in rows
    ]


def item_notes(con, item_id):
    rows = con.execute(
        "SELECT i.key AS key, n.note AS note"
        " FROM itemNotes n JOIN items i ON i.itemID = n.itemID"
        " WHERE n.parentItemID = ?"
        "   AND i.itemID NOT IN (SELECT itemID FROM deletedItems)",
        (item_id,),
    ).fetchall()
    out = []
    for r in rows:
        note = re.sub(r"<[^>]+>", " ", r["note"] or "")
        note = re.sub(r"\s+", " ", note).strip()
        out.append({"key": r["key"], "note": note[:2000]})
    return out


def item_payload(con, item_id, key, type_name=None):
    if type_name is None:
        row = con.execute(
            "SELECT it.typeName AS t FROM items i JOIN itemTypes it ON it.itemTypeID = i.itemTypeID"
            " WHERE i.itemID = ?",
            (item_id,),
        ).fetchone()
        type_name = row["t"] if row else None
    fields = item_fields(con, item_id)
    atts = item_attachments(con, item_id, key)
    annos = item_annotations(con, [a["itemID"] for a in atts])
    date = fields.get("date") or ""
    return {
        "itemID": item_id,
        "key": key,
        "itemType": type_name,
        "title": fields.get("title"),
        "creators": item_creators(con, item_id),
        "year": date[:4] if date[:4].isdigit() else None,
        "date": date,
        "publication": fields.get("publicationTitle"),
        "doi": fields.get("DOI"),
        "url": fields.get("url"),
        "abstract": fields.get("abstractNote"),
        "extra": fields.get("extra"),
        "attachments": atts,
        "annotationCount": len(annos),
        "annotations": annos,
        "notes": item_notes(con, item_id),
    }


def search(con, title, author, year, limit):
    sql = [
        "SELECT DISTINCT i.itemID AS itemID, i.key AS key, it.typeName AS typeName, idv.value AS title",
        "FROM itemData id",
        "JOIN fields f ON f.fieldID = id.fieldID",
        "JOIN itemDataValues idv ON idv.valueID = id.valueID",
        "JOIN items i ON i.itemID = id.itemID",
        "JOIN itemTypes it ON it.itemTypeID = i.itemTypeID",
        "WHERE f.fieldName = 'title'",
        "  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)",
        "  AND it.typeName NOT IN ('attachment','note','annotation')",
    ]
    params = []
    if title:
        sql.append("AND lower(idv.value) LIKE ?")
        params.append("%" + title.lower() + "%")
    if author:
        sql.append(
            "AND i.itemID IN (SELECT ic.itemID FROM itemCreators ic"
            " JOIN creators c ON c.creatorID = ic.creatorID"
            " WHERE lower(c.lastName) LIKE ? OR lower(c.firstName) LIKE ?)"
        )
        params += ["%" + author.lower() + "%", "%" + author.lower() + "%"]
    if year:
        sql.append(
            "AND i.itemID IN (SELECT id2.itemID FROM itemData id2"
            " JOIN fields f2 ON f2.fieldID = id2.fieldID"
            " JOIN itemDataValues v2 ON v2.valueID = id2.valueID"
            " WHERE f2.fieldName = 'date' AND v2.value LIKE ?)"
        )
        params.append(str(year) + "%")
    sql.append("ORDER BY idv.value LIMIT ?")
    params.append(limit)
    rows = con.execute(" ".join(sql), params).fetchall()
    return [item_payload(con, r["itemID"], r["key"], r["typeName"]) for r in rows]


def main():
    ap = argparse.ArgumentParser(description="Zotero 只读查询")
    ap.add_argument("--title", help="标题关键词（模糊）")
    ap.add_argument("--author", help="作者姓/名关键词")
    ap.add_argument("--year", help="年份，如 2026")
    ap.add_argument("--key", help="Zotero item key，精确匹配")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if not os.path.isfile(ZOTERO_DB):
        print(json.dumps({"error": "Zotero 数据库不存在: " + ZOTERO_DB}, ensure_ascii=False))
        sys.exit(1)
    try:
        con = open_db()
    except Exception as e:
        print(json.dumps({"error": "数据库快照/打开失败: " + str(e)}, ensure_ascii=False))
        sys.exit(1)

    try:
        if args.key:
            row = con.execute(
                "SELECT i.itemID AS itemID, i.key AS key, it.typeName AS typeName"
                " FROM items i JOIN itemTypes it ON it.itemTypeID = i.itemTypeID"
                " WHERE i.key = ?",
                (args.key.upper(),),
            ).fetchone()
            if not row:
                print(json.dumps({"error": "找不到 item key: " + args.key}, ensure_ascii=False))
                sys.exit(2)
            out = item_payload(con, row["itemID"], row["key"], row["typeName"])
            out["matchCount"] = 1
            print(json.dumps(out, ensure_ascii=False, indent=2))
        elif args.title or args.author or args.year:
            matches = search(con, args.title, args.author, args.year, args.limit)
            print(json.dumps({"matchCount": len(matches), "matches": matches}, ensure_ascii=False, indent=2))
        else:
            n_items = con.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
            n_annos = con.execute("SELECT COUNT(*) AS c FROM itemAnnotations").fetchone()["c"]
            print(json.dumps(
                {
                    "ok": True,
                    "db": ZOTERO_DB,
                    "snapshot": SNAPSHOT_DIR,
                    "items": n_items,
                    "annotations": n_annos,
                    "hint": "用 --title/--author/--year 搜索，或 --key 精确取条目",
                },
                ensure_ascii=False,
                indent=2,
            ))
    finally:
        con.close()


if __name__ == "__main__":
    main()
