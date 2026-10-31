import asyncio

import pytest
from pydantic import ValidationError

from app.api_resources import ProjectPatch, ResourceRef, ServiceIn
from app.connectors import probe_http


@pytest.mark.parametrize('url', ['https://example.com:bad/health',
                                 'https://example.com:99999/health'])
def test_service_and_readiness_urls_reject_invalid_ports(url):
    with pytest.raises(ValidationError):
        ServiceIn(name='service', health_url=url)
    with pytest.raises(ValidationError):
        ResourceRef(readiness_url=url)


@pytest.mark.parametrize('url', ['https://user:password@github.com/owner/repo',
                                 'https://example.com/owner/repo', 'not a URL'])
def test_project_patch_rejects_invalid_repository_urls(url):
    with pytest.raises(ValidationError):
        ProjectPatch(repo_url=url)


def test_project_patch_normalizes_repository_like_creation():
    assert ProjectPatch(repo_url='git@github.com:owner/repo.git').repo_url == 'https://github.com/owner/repo'
    assert ProjectPatch(repo_url=None).repo_url is None


@pytest.mark.parametrize('url', ['https://example.com:bad/health', 'https://[invalid/health'])
def test_previously_stored_malformed_targets_report_unknown(url):
    result = asyncio.run(probe_http(url, timeout=1, expected_status=200, allow_private=False))
    assert result.status == 'unknown'
