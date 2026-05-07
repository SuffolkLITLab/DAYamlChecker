import pytest
from dayamlchecker.check_questions_urls import is_reserved_example_domain


@pytest.mark.parametrize(
    "url,expected",
    [
        # RFC 2606 / RFC 6761 special-use example domains
        ("http://example.com", True),
        ("https://example.org", True),
        ("https://example.net", True),
        ("http://my.example.com", True),
        ("https://sub.sub.example.org", True),
        ("http://another.example.net", True),
        ("https://example.com/path", True),
        # RFC 2606 / RFC 6761 special-use TLDs
        ("http://example", True),
        ("https://test", True),
        ("http://invalid", True),
        ("https://localhost", True),
        ("http://my.example", True),
        ("https://sub.test", True),
        ("http://something.invalid", True),
        ("https://dev.localhost", True),
        # IANA-managed example domain, but not in the RFC 6761 registry
        ("http://example.edu", True),
        ("http://my.example.edu", True),
        # Similar-looking real domains should still be checked
        ("https://notexample.com", False),
        ("https://example.com.untrusted.com", False),
        ("https://example.edu.untrusted.edu", False),
        ("https://google.com", False),
        ("https://suffolklitlab.org", False),
    ],
)
def test_is_reserved_example_domain(url: str, expected: bool) -> None:
    assert is_reserved_example_domain(url) == expected
