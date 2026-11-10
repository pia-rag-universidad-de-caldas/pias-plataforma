"""Where the pipeline may POST an actor's notice (feature 040): only allowed hosts, never metadata-like addresses."""

import pytest

from pipeline.domain.callbacks import address_problem, allowed_hosts, url_problem

HOSTS = allowed_hosts("lab.local, 10.0.0.5, 169.254.169.254")


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9000/hook", "http://localhost/hook", "http://[::1]:9000/hook", "https://LAB.local/hook"],
)
def test_an_allowed_host_is_accepted(url: str) -> None:
    assert url_problem(url, HOSTS) is None


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://localhost/x", "localhost/hook", "not a url"])
def test_only_http_and_https_are_accepted(url: str) -> None:
    assert url_problem(url, HOSTS) is not None


@pytest.mark.parametrize("url", ["http://[bad", "http://localhost:notaport/x", "http://", "http://u:p@localhost/x"])
def test_a_malformed_url_or_one_with_credentials_is_rejected(url: str) -> None:
    assert url_problem(url, HOSTS) is not None


def test_a_host_outside_the_list_is_rejected() -> None:
    assert "allowed" in (url_problem("http://example.com/hook", HOSTS) or "")


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data", "http://[::ffff:169.254.169.254]/x"])
def test_a_forbidden_address_is_rejected_even_if_listed(url: str) -> None:
    hosts = allowed_hosts("169.254.169.254, ::ffff:169.254.169.254")
    assert "forbidden" in (url_problem(url, hosts) or "")


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "fe80::1", "224.0.0.1", "ff02::1", "0.0.0.0", "::", "100.100.100.200"]
)
def test_link_local_metadata_multicast_and_unspecified_are_forbidden(address: str) -> None:
    assert address_problem(address) is not None


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "10.0.0.5", "8.8.8.8"])
def test_other_addresses_are_not_forbidden_by_themselves(address: str) -> None:
    assert address_problem(address) is None


def test_the_variable_adds_hosts_to_loopback() -> None:
    assert allowed_hosts("Lab.Local,, ") == {"localhost", "127.0.0.1", "::1", "lab.local"}


def test_without_the_variable_only_loopback_is_allowed() -> None:
    assert allowed_hosts(None) == {"localhost", "127.0.0.1", "::1"}
