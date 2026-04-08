import click
from nexus.cli.utils import _get_service, REPO_ROOT, _log_perf_span, _io_queue

@click.group(name="wisdom")
def wisdom_group():
    """🧠 聯邦智慧結晶與經驗管理"""
    pass

@wisdom_group.command("sync")
@click.option("--peer", help="Peer address for P2P sync")
@click.option("--pull-eternal", is_flag=True, help="Fetch shared lessons from Arweave")
def sync(peer, pull_eternal):
    """🛡️ 啟動聯邦經驗同步 (P2P/Arweave)"""
    _get_service().wisdom_sync(peer, pull_eternal)

@wisdom_group.command("audit-risk")
@click.argument("file_path")
def audit_risk(file_path):
    """🛡️ [Spec-Lock] 物理攔截違憲變更 (Constitution Guard)"""
    _get_service().wisdom_audit_risk(file_path)

@wisdom_group.command("lookup")
@click.argument("query")
@click.option("--top-k", default=5)
def lookup(query, top_k):
    """🔍 檢索全球聯邦結晶智庫"""
    _get_service().wisdom_lookup(query, top_k)

@wisdom_group.command("feedback")
@click.argument("reason")
@click.option("--status", default="VETOED")
def feedback(reason, status):
    """📝 寫入治理回饋 (Veto/Decision)"""
    _get_service().wisdom_feedback(reason, status)

@wisdom_group.command("stats")
def stats():
    """📊 查看智慧結晶與 ROI 統計數據"""
    _get_service().wisdom_stats()
