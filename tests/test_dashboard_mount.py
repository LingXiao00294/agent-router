from __future__ import annotations

from pathlib import Path

from agent_router.app import resolve_dashboard_dist


class TestResolveDashboardDist:
    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert resolve_dashboard_dist() is None

    def test_finds_cwd_dashboard_dist(self, tmp_path, monkeypatch):
        dist = tmp_path / "dashboard" / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html></html>")
        monkeypatch.chdir(tmp_path)
        result = resolve_dashboard_dist()
        assert result is not None
        assert result.resolve() == dist.resolve()

    def test_finds_project_root_dashboard_dist(self):
        project_root = Path(__file__).resolve().parent.parent
        dist = project_root / "dashboard" / "dist"
        if dist.is_dir():
            result = resolve_dashboard_dist()
            assert result is not None
            assert result.is_dir()


    def test_finds_wheel_layout_dashboard_dist(self, tmp_path, monkeypatch):
        """模拟 wheel 安装: site-packages/agent_router + site-packages/dashboard/dist."""
        site = tmp_path / "site-packages"
        pkg = site / "agent_router"
        pkg.mkdir(parents=True)
        dist = site / "dashboard" / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html></html>")
        fake_app = pkg / "app.py"
        fake_app.write_text("# stub")
        import agent_router.app as app_mod
        monkeypatch.setattr(app_mod, "__file__", str(fake_app))
        monkeypatch.chdir(tmp_path)
        result = app_mod.resolve_dashboard_dist()
        assert result is not None
        assert result.resolve() == dist.resolve()
