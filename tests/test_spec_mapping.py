import pytest

from bugbot import spec_mapping


@pytest.fixture(scope="session")
def spec_mapper():
    return spec_mapping.SpecMapper.load()


@pytest.mark.parametrize(
    ["urls", "product", "component"],
    [
        (
            ["https://drafts.csswg.org/css-fonts-4#foo"],
            "Core",
            "Layout: Text and Fonts",
        ),
        (
            [
                "https://drafts.csswg.org/some-default-path",
            ],
            "Core",
            "Layout: General",
        ),
        (
            [
                "https://example.org",
            ],
            "Core",
            "General",
        ),
        (
            [
                "https://drafts.csswg.org/css-fonts-4#foo",
                "https://drafts.csswg.org/css-values-2#foo",
            ],
            "Core",
            "CSS Parsing and Computation",
        ),
        (
            [
                "https://w3c.github.io/web-share",
                "https://drafts.csswg.org/some-default-path",
            ],
            "Core",
            "DOM: Web Share",
        ),
    ],
)
def test_map_urls(spec_mapper, urls, product, component):
    assert spec_mapper.map_urls(urls) == (product, component)
