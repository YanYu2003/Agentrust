"""
数据库迁移脚本：升级审计日志表，新增链路追踪字段
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine
from sqlalchemy import text


async def migrate_audit_logs():
    """升级审计日志表结构"""
    print("开始升级审计日志表结构...")
    
    async with engine.begin() as conn:
        # 新增task_id字段
        await conn.execute(text("""
            ALTER TABLE audit_logs 
            ADD COLUMN task_id TEXT DEFAULT NULL
        """))
        print("✅ 新增 task_id 字段完成")
        
        # 新增parent_agent_id字段
        await conn.execute(text("""
            ALTER TABLE audit_logs 
            ADD COLUMN parent_agent_id TEXT DEFAULT NULL
        """))
        print("✅ 新增 parent_agent_id 字段完成")
        
        # 新增task_context字段
        await conn.execute(text("""
            ALTER TABLE audit_logs 
            ADD COLUMN task_context TEXT DEFAULT '{}'
        """))
        print("✅ 新增 task_context 字段完成")
        
        # 新增索引
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_task_id 
            ON audit_logs(task_id)
        """))
        print("✅ 新增 task_id 索引完成")
        
        # 更新schema版本
        await conn.execute(text("""
            INSERT OR REPLACE INTO schema_version (version, description)
            VALUES (2, 'Added audit tracing fields: task_id, parent_agent_id, task_context')
        """))
        
        # 验证升级结果
        result = await conn.execute(text("PRAGMA table_info(audit_logs)"))
        columns = [row[1] for row in result.fetchall()]
        required_columns = {"task_id", "parent_agent_id", "task_context"}
        
        if required_columns.issubset(columns):
            print("\n✅ 审计日志表升级成功！")
            print("当前表字段：", ", ".join(columns))
        else:
            missing = required_columns - set(columns)
            print(f"\n❌ 升级失败，缺少字段：{missing}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(migrate_audit_logs())
