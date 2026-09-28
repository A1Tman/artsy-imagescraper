"""Select images by page identity before ranking their available resolutions.

Only group URLs when the page (srcset/picture/link) or a known CDN path provides
evidence that they are variants of the same image. Never strip arbitrary queries:
they can contain signatures or identify entirely different images.
"""
from dataclasses import dataclass, field
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

ARTSY_IMAGE_HOST = "d32dm0rphc51dk.cloudfront.net"
ARTSY_PROXY_HOSTS = {"d7hftxdivxxvm.cloudfront.net", "images.artsy.net"}
VERSIONS = ("original", "main", "larger", "large", "normalized", "medium", "small", "square")
IMAGE_SUFFIX = re.compile(r"\.(?:jpe?g|png|webp|gif|bmp|avif|tiff?)(?:$|[?#])", re.I)
RESIZED_NAME = re.compile(r"-\d+x\d+(?:-\d+)?(?=\.[^.]+$)")


@dataclass
class ImageGroup:
    urls: list[str] = field(default_factory=list)
    reason: str = "page image"


def asset_url(page_url, value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        url = urljoin(page_url, value.strip())
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return None
        if len(parts.hostname) > 253 or len(url) > 8192:
            return None
        if parts.port not in (None, 80, 443):
            return None
        return urlunsplit(parts._replace(fragment=""))
    except ValueError:
        return None


def unwrap_artsy(url):
    """Decode the wrapper's src value once, preserving the source URL's query."""
    for _ in range(3):
        parts = urlsplit(url)
        if parts.hostname not in ARTSY_PROXY_HOSTS:
            break
        value = parse_qs(parts.query).get("src", [None])[0]
        resolved = asset_url(url, value)
        if not resolved or resolved == url:
            break
        url = resolved
    return url


def image_key(url):
    url = unwrap_artsy(url)
    parts = urlsplit(url)
    path = parts.path
    # This host has /<image-id>/<version>.<format>; other CDNs do not.
    segments = path.strip("/").split("/")
    if parts.hostname == ARTSY_IMAGE_HOST and len(segments) == 2:
        return (parts.hostname, segments[0], parts.query)
    return (parts.netloc.lower(), RESIZED_NAME.sub("", path), parts.query)


def srcset_urls(value, page_url):
    result = []
    if not isinstance(value, str):
        return result
    # URLs may contain commas (e.g. image CDN transformation paths). Split at
    # descriptor boundaries, not every comma. Data URLs are deliberately ignored.
    for match in re.finditer(r"(?:^|,\s*)(\S+?)\s+(\d+(?:\.\d+)?)(w|x)(?=\s*(?:,|$))", value):
        url = asset_url(page_url, match[1])
        if url:
            result.append((float(match[2]), url))
    if not result:
        url = asset_url(page_url, value.rstrip(", "))
        if url and not re.search(r"\s", value.strip()):
            result.append((1, url))
    return [url for _, url in sorted(result, key=lambda pair: (-pair[0], pair[1]))]


def walk_json(value, depth=0):
    if depth > 35:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child, depth + 1)


def page_identity(value):
    if not isinstance(value, str):
        return ""
    return urlsplit(value).path.rstrip("/")


def json_documents(soup):
    for tag in soup.find_all("script"):
        if tag.get("type") not in ("application/ld+json", "application/json"):
            continue
        raw = tag.string
        if not raw or len(raw) > 5_000_000:
            continue
        try:
            yield tag.get("type"), json.loads(raw)
        except (ValueError, RecursionError):
            continue


def image_values(value):
    """Read only image fields, never a related artwork's nested images."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [url for child in value for url in image_values(child)]
    if not isinstance(value, dict):
        return []
    urls = []
    template = value.get("imageURL") or value.get("image_url")
    versions = value.get("imageVersions") or value.get("image_versions") or []
    if isinstance(template, str):
        for version in VERSIONS:
            if version in versions:
                urls.append(template.replace(":version", version).replace("{image_version}", version))
        if ":version" not in template and "{image_version}" not in template:
            urls.append(template)
    for key in ("contentUrl", "url", "src", "original", "large", "resized"):
        if key in value:
            urls.extend(image_values(value[key]))
    for key in ("srcSet", "srcset"):
        if isinstance(value.get(key), str):
            urls.extend(srcset_urls(value[key], "https://www.artsy.net"))
    return urls


def structured_groups(soup, page_url, artsy):
    target = page_identity(page_url)
    slug = target.rsplit("/", 1)[-1]
    matches, unnamed = [], []
    for kind, document in json_documents(soup):
        for node in walk_json(document):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list):
                continue
            accepted = ("VisualArtwork", "Product") if artsy else ("VisualArtwork", "Product", "Article", "NewsArticle", "BlogPosting")
            is_ld_subject = kind == "application/ld+json" and any(t in accepted for t in types)
            is_artsy_subject = artsy and node.get("slug") == slug and any(k in node for k in ("image", "images", "figures"))
            if not is_ld_subject and not is_artsy_subject:
                continue
            identity = node.get("url") or node.get("@id") or node.get("mainEntityOfPage")
            if isinstance(identity, dict):
                identity = identity.get("@id")
            if identity and page_identity(identity) != target and not is_artsy_subject:
                continue
            fields = [node.get("image")]
            if is_artsy_subject:
                figures = node.get("figures") or node.get("images") or []
                if isinstance(figures, list):
                    figures = sorted(figures, key=lambda v: not (isinstance(v, dict) and v.get("isDefault")))
                    fields.extend(figures)
            urls = [u for field in fields for u in image_values(field)]
            groups = []
            for raw in urls:
                url = asset_url(page_url, raw)
                if url:
                    merge_group(groups, ImageGroup([unwrap_artsy(url)], "matching page metadata"))
            if identity or is_artsy_subject:
                matches.extend(groups)
            else:
                unnamed.extend(groups)
    # Ambiguous unlabelled products on collection pages must not silently become
    # the main artwork. A single unlabelled subject is a reasonable fallback.
    merged = []
    for group in matches or unnamed:
        merge_group(merged, group)
    return merged if matches or len(merged) == 1 else []


def merge_group(groups, candidate):
    keys = {image_key(u) for u in candidate.urls}
    overlaps = [g for g in groups if keys.intersection(image_key(u) for u in g.urls)]
    if not overlaps:
        groups.append(candidate)
        return
    first = overlaps[0]
    first.urls = list(dict.fromkeys(first.urls + candidate.urls + [u for g in overlaps[1:] for u in g.urls]))
    for other in overlaps[1:]:
        groups.remove(other)


def element_group(img, page_url):
    urls = []
    parent = getattr(img, "parent", None)
    if getattr(parent, "name", None) == "picture":
        for source in parent.find_all("source"):
            urls.extend(srcset_urls(source.get("srcset", source.get("data-srcset", "")), page_url))
    for key in ("srcset", "data-srcset"):
        urls.extend(srcset_urls(img.get(key, ""), page_url))
    for key in ("data-original", "data-full", "data-large", "data-src", "src"):
        url = asset_url(page_url, img.get(key))
        if url:
            urls.append(url)
    if hasattr(img, "find_parent"):
        anchor = img.find_parent("a", href=True)
        if anchor and IMAGE_SUFFIX.search(anchor["href"]):
            linked = asset_url(page_url, anchor["href"])
            if linked:
                urls.insert(0, linked)
    return ImageGroup(list(dict.fromkeys(unwrap_artsy(u) for u in urls)), "main content image")


def variants(group, artsy):
    urls = list(dict.fromkeys(group.urls))
    if artsy:
        # Public Artsy assets can expose a larger version than their social card.
        # These are candidates, not claims that an original exists. The downloader
        # checks status, format and pixel dimensions and keeps the best valid file.
        for url in tuple(urls):
            parts = urlsplit(url)
            segments = parts.path.strip("/").split("/")
            if parts.hostname == ARTSY_IMAGE_HOST and len(segments) == 2 and not parts.query:
                stem, dot, suffix = segments[-1].rpartition(".")
                if dot and stem in VERSIONS:
                    for version in VERSIONS[:5]:
                        candidate = urlunsplit(parts._replace(path=f"/{segments[0]}/{version}.{suffix}"))
                        if candidate not in urls:
                            urls.append(candidate)
    # Stable order matters when pixel dimensions tie. Prefer the actual original
    # or largest advertised version over a social-card rendition of equal size.
    def rank(url):
        stem = urlsplit(url).path.rsplit("/", 1)[-1].split(".")[0]
        return VERSIONS.index(stem) if artsy and stem in VERSIONS else len(VERSIONS)
    return ImageGroup(sorted(urls, key=rank)[:10], group.reason)


def select_image_groups(soup, page_url, config, artsy=False):
    subjects = structured_groups(soup, page_url, artsy)
    social = []
    for attr, value in (("property", "og:image"), ("name", "twitter:image"), ("property", "twitter:image")):
        tag = soup.find("meta", attrs={attr: value})
        url = asset_url(page_url, tag.get("content")) if tag else None
        if url:
            merge_group(social, ImageGroup([unwrap_artsy(url)], "page preview image"))
    primary = subjects or social[:1]
    root = None
    artwork_root = None
    if hasattr(soup, "select_one"):
        if artsy:
            artwork_root = soup.select_one('[data-test="artworkImage"], [data-test="artwork-image"]')
            root = artwork_root
        root = root or soup.select_one("article") or soup.select_one("main")
    scope = root or soup
    content = []
    for img in scope.find_all("img"):
        if hasattr(img, "find_parent") and img.find_parent(["nav", "header", "footer", "aside"]):
            continue
        if hasattr(img, "find_parent"):
            anchor = img.find_parent("a", href=True)
            if anchor and not IMAGE_SUFFIX.search(anchor["href"]):
                destination = asset_url(page_url, anchor["href"])
                if destination and page_identity(destination) != page_identity(page_url):
                    continue  # related-work cards and navigation
        group = element_group(img, page_url)
        terms = set(config.unwanted_image_terms) - {"source", "larger", "small", "square"}
        if group.urls and not all(any(term in re.split(r"[^a-z0-9]+", urlsplit(u).path.lower()) for term in terms) for u in group.urls):
            merge_group(content, group)
    # srcset/picture/link associates differently named variants with the primary.
    # Only matching assets augment primary selection; arbitrary preloads and CSS
    # backgrounds are not evidence that an image belongs to the artwork.
    if not subjects and content and root is not None:
        social_keys = {image_key(u) for g in social for u in g.urls}
        matching_content = [g for g in content if social_keys.intersection(image_key(u) for u in g.urls)]
        # A real artwork gallery is stronger evidence than a generic social card.
        # For article pages use the first main-content image if the card cannot
        # be associated with any displayed image (often the site's brand image).
        if artwork_root is not None or not matching_content:
            primary = content[:1]
    selected = []
    for group in primary:
        merge_group(selected, group)
    for group in content:
        if not primary or config.image_selection == "content" or any(
            {image_key(u) for u in group.urls}.intersection(image_key(u) for u in p.urls) for p in selected
        ):
            merge_group(selected, group)
    if config.image_selection == "primary":
        selected = selected[:1]
    return [variants(group, artsy) for group in selected[:config.max_images]]
