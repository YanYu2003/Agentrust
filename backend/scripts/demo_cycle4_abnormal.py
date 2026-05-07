#!/usr/bin/env python3
"""
第四周期 - 异常 / 越权演示脚本

  A) 企业数据 Agent：外部检索身份调用 /read -> HTTP 403（白名单拦截）
  B) IAM：仅有 read_database 能力的 Agent 请求 read_bitable -> DENIED 审计

环境变量：
  IAM_BASE          默认 http://127.0.0.1:8000/api/v1
  ENTERPRISE_URL    默认 http://127.0.0.1:8001/api/v1
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.crypto.keys import generate_agent_keypair, load_private_key_pem
from app.crypto.signature import sign_data

IAM_BASE = os.environ.get("IAM_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
ENTERPRISE_URL = os.environ.get("ENTERPRISE_URL", "http://127.0.0.1:8001/api/v1").rstrip("/")


async def _auth_session(client: httpx.AsyncClient, agent_id: str, cert_id: str, private_pem: bytes) -> str:
    ch = await client.post(f"{IAM_BASE}/ca/auth/challenge", json={"agent_id": agent_id, "cert_id": cert_id})
    ch.raise_for_status()
    cj = ch.json()
    sig = sign_data(load_private_key_pem(private_pem), cj["nonce"].encode())
    vr = await client.post(
        f"{IAM_BASE}/ca/auth/verify",
        json={
            "challenge_id": cj["challenge_id"],
            "agent_id": agent_id,
            "signed_nonce": base64.b64encode(sig).decode(),
        },
    )
    vr.raise_for_status()
    return vr.json()["session_token"]


async def _phase_enterprise_block(task_id: str) -> None:
    payload = {
        "task_id": task_id,
        "caller_agent_id": "agent-external-search",
        "resource_type": "bitable",
        "resource_id": "app_test/tbl_sales",
        "params": {"fields": ["name", "sales"]},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.post(f"{ENTERPRISE_URL}/read", json=payload)
            if r.status_code == 403:
                print("[Agents] 预期 403 拒绝（非文档助手调用企业数据）:", r.json())
                return
            print("[Agents] UNEXPECTED status:", r.status_code, r.text[:400])
    except httpx.ConnectError:
        print("[Agents] SKIP: Enterprise Agent 不可达（:8001）")


async def _phase_iam_denied(task_id: str) -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        priv, pub = generate_agent_keypair()
        reg = await client.post(
            f"{IAM_BASE}/ca/register",
            json={
                "name": f"cycle4-deny-{uuid.uuid4().hex[:6]}",
                "public_key": pub.decode(),
                "owner": "cycle4-demo",
                "requested_capabilities": ["read_database"],
                "description": "Cycle4 abnormal - limited caps",
                "trust_level": 4,
            },
        )
        reg.raise_for_status()
        data = reg.json()
        agent_id = data["agent_id"]
        cert_id = data["certificate"]["cert_id"]
        cap_db = next(t["token_id"] for t in data["capability_tokens"] if t["capability"] == "read_database")

        session = await _auth_session(client, agent_id, cert_id, priv)
        headers = {"Authorization": f"Bearer {session}"}
        body = {
            "action": "read_bitable",
            "resource": "app_xxx:tbl_sales",
            "token_chain": [
                {"token_id": cert_id, "token_type": "certificate"},
                {"token_id": cap_db, "token_type": "capability"},
            ],
            "task_id": task_id,
            "parent_agent_id": "agent-external-search",
            "task_context": {"demo": "cycle4_abnormal"},
        }
        r = await client.post(f"{IAM_BASE}/resources/execute", headers=headers, json=body)
        if r.status_code == 200:
            print("[IAM] UNEXPECTED 200:", r.text[:400])
            return
        print("[IAM] 预期拒绝 HTTP", r.status_code, ":", json.dumps(r.json(), ensure_ascii=False)[:500])

        logs = await client.get(f"{IAM_BASE}/audit/logs", headers=headers, params={"task_id": task_id, "page_size": 20})
        logs.raise_for_status()
        lj = logs.json()
        print(f"[IAM] 审计条数 task_id={task_id}: total={lj['total']}")

        print("\n=== 异常演示完成 ===")
        print(f"task_id（Dashboard「任务链路」可查 IAM 拒绝步骤）: {task_id}")
        print(f"agent_id（本 run 注册）: {agent_id}")
        print(f"cert_id（Dashboard 占位登录挑战时用）: {cert_id}")
        print("session_token（本地演示用，勿提交公开仓库）:")
        print(session)
        print(
            "查看链路: Swagger Authorize 粘贴 Bearer 后 GET "
            f"/api/v1/audit/trace/{task_id}"
            "；或同上 token 写入 Dashboard localStorage。"
        )


async def main() -> None:
    task_id = f"cycle4-abnormal-{uuid.uuid4().hex[:12]}"
    print("Cycle4 ABNORMAL demo  task_id =", task_id)
    await _phase_enterprise_block(task_id)
    await _phase_iam_denied(task_id)


if __name__ == "__main__":
    asyncio.run(main())
