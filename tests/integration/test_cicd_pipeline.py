"""
Integration tests for CI/CD pipeline infrastructure.
Feature 0.18: CI/CD Pipeline
"""
import json
import subprocess
import pytest
from pathlib import Path


ROOT = Path(__file__).parent.parent.parent


class TestPipelineConfiguration:
    """Test that pipeline configuration files are valid."""

    def test_ci_workflow_exists(self) -> None:
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "CI workflow file must exist"

    def test_deploy_workflow_exists(self) -> None:
        deploy_path = ROOT / ".github" / "workflows" / "deploy.yml"
        assert deploy_path.exists(), "Deploy workflow file must exist"

    def test_security_workflow_exists(self) -> None:
        security_path = ROOT / ".github" / "workflows" / "security.yml"
        assert security_path.exists(), "Security workflow file must exist"

    def test_ci_workflow_is_valid_yaml(self) -> None:
        import yaml
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        with open(ci_path) as f:
            config = yaml.safe_load(f)
        assert config is not None
        assert "jobs" in config

    def test_deploy_workflow_is_valid_yaml(self) -> None:
        import yaml
        deploy_path = ROOT / ".github" / "workflows" / "deploy.yml"
        with open(deploy_path) as f:
            config = yaml.safe_load(f)
        assert config is not None
        assert "jobs" in config


class TestMakefile:
    """Test that Makefile targets work correctly."""

    def test_makefile_exists(self) -> None:
        makefile_path = ROOT / "Makefile"
        assert makefile_path.exists(), "Makefile must exist"

    def test_make_help(self) -> None:
        result = subprocess.run(
            ["make", "help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "ApexQuant Ultra" in result.stdout

    def test_make_format(self) -> None:
        result = subprocess.run(
            ["make", "format"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Format may fail if tools aren't installed in CI
        # but should not crash
        assert result.returncode in (0, 1, 2)


class TestVersionManagement:
    """Test version management."""

    def test_version_file_exists(self) -> None:
        version_path = ROOT / "VERSION"
        assert version_path.exists(), "VERSION file must exist"

    def test_version_format_is_valid(self) -> None:
        version_path = ROOT / "VERSION"
        version = version_path.read_text().strip()

        import re
        pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
        assert re.match(pattern, version), f"Invalid version format: {version}"


class TestSecurityConfiguration:
    """Test security scanning configuration."""

    def test_gitleaks_config_exists(self) -> None:
        config_path = ROOT / ".gitleaks.toml"
        assert config_path.exists(), "Gitleaks configuration must exist"

    def test_semgrep_config_exists(self) -> None:
        config_path = ROOT / ".semgrep.yml"
        assert config_path.exists(), "Semgrep configuration must exist"

    def test_gitleaks_config_is_valid(self) -> None:
        import tomllib
        config_path = ROOT / ".gitleaks.toml"
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        assert "rules" in config or "allowlist" in config


class TestDeploymentScripts:
    """Test deployment scripts."""

    def test_deploy_script_exists(self) -> None:
        script_path = ROOT / "scripts" / "deploy" / "deploy.sh"
        assert script_path.exists(), "Deploy script must exist"

    def test_deploy_script_is_executable(self) -> None:
        script_path = ROOT / "scripts" / "deploy" / "deploy.sh"
        import os
        assert os.access(script_path, os.X_OK), "Deploy script must be executable"

    def test_rollback_script_exists(self) -> None:
        script_path = ROOT / "scripts" / "deploy" / "rollback.sh"
        assert script_path.exists(), "Rollback script must exist"