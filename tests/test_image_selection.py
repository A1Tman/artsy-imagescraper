import json
import unittest
from bs4 import BeautifulSoup
from config import ScraperConfig
from image_selection import image_key, select_image_groups, srcset_urls, unwrap_artsy

PAGE = "https://www.artsy.net/artwork/artist-target"
CDN = "https://d32dm0rphc51dk.cloudfront.net/"


class SelectionTests(unittest.TestCase):
    def select(self, html, artsy=False, mode="primary"):
        return select_image_groups(BeautifulSoup(html, "html.parser"), PAGE,
                                   ScraperConfig(image_selection=mode), artsy)

    def test_artsy_matches_page_not_first_related_product(self):
        nodes = [
            {"@type": "VisualArtwork", "url": PAGE + "-related", "image": CDN + "other/large.jpg"},
            {"@type": ["Product", "VisualArtwork"], "url": PAGE, "image": {"contentUrl": CDN + "target/large.jpg"}},
        ]
        html = f'<script type="application/ld+json">{json.dumps(nodes)}</script>'
        html += f'<link rel="preload" as="image" href="{CDN}unrelated/main.jpg">'
        html += f'<meta property="og:image" content="{CDN}social/main.jpg">'
        html += f'<img src="{CDN}recommendation/large.jpg">'
        groups = self.select(html, artsy=True)
        self.assertEqual(len(groups), 1)
        self.assertTrue(all("/target/" in u for u in groups[0].urls))
        self.assertIn(CDN + "target/larger.jpg", groups[0].urls)

    def test_wrapper_preserves_signed_inner_query_and_encoding(self):
        original = CDN + "target/large.jpg?token=a%2Fb&expires=123"
        from urllib.parse import quote
        wrapper = "https://d7hftxdivxxvm.cloudfront.net/?width=600&src=" + quote(original, safe="")
        self.assertEqual(unwrap_artsy(wrapper), original)
        unknown = "https://example.com/image?src=" + quote(original, safe="")
        self.assertEqual(unwrap_artsy(unknown), unknown)

    def test_srcset_bridges_different_filenames_to_social_image(self):
        html = '''<meta property="og:image" content="/small.jpg">
        <main><img src="/small.jpg" srcset="/small.jpg 400w, /full.jpg 2000w">
        <img src="/unrelated.jpg"></main><img src="/avatar.jpg">
        <link rel="preload" as="image" href="/ad.jpg">'''
        groups = self.select(html)
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0].urls), {"https://www.artsy.net/small.jpg", "https://www.artsy.net/full.jpg"})

    def test_lazy_picture_and_linked_original_form_one_group(self):
        html = '''<main><a href="/original.png"><picture>
        <source srcset="/mobile.webp 1x, /retina.webp 2x">
        <img data-src="/lazy.jpg" src="data:image/gif;base64,AA"></picture></a></main>'''
        group, = self.select(html)
        self.assertEqual(len(group.urls), 4)
        self.assertEqual(group.urls[0], "https://www.artsy.net/original.png")

    def test_content_mode_excludes_chrome_and_related_cards(self):
        html = '''<header><img src="/header.jpg"></header><main>
        <img src="/one.jpg"><img src="/two.jpg">
        <a href="/artwork/related"><img src="/related.jpg"></a>
        <aside><img src="/ad.jpg"></aside></main><footer><img src="/footer.jpg"></footer>'''
        self.assertEqual(len(self.select(html)), 1)
        groups = self.select(html, mode="content")
        self.assertEqual([g.urls[0].rsplit("/", 1)[-1] for g in groups], ["one.jpg", "two.jpg"])

    def test_distinct_query_identifiers_are_not_collapsed(self):
        self.assertNotEqual(image_key("https://example.com/image?id=1"), image_key("https://example.com/image?id=2"))
        self.assertNotEqual(image_key("https://other.cloudfront.net/images/a.jpg"), image_key("https://other.cloudfront.net/images/b.jpg"))

    def test_srcset_density_and_commas_in_cdn_paths(self):
        value = "https://cdn.example.com/w_400,q_90/photo.jpg 1x, https://cdn.example.com/w_800,q_90/photo.jpg 2x"
        urls = srcset_urls(value, PAGE)
        self.assertEqual(urls, ["https://cdn.example.com/w_800,q_90/photo.jpg", "https://cdn.example.com/w_400,q_90/photo.jpg"])

    def test_hydrated_artwork_images_do_not_include_related_objects(self):
        document = {"artwork": {"slug": "artist-target", "figures": [
            {"__typename": "Image", "isDefault": True, "imageURL": CDN + "target/:version.jpg", "imageVersions": ["large", "original"]}],
            "related": {"image": {"url": CDN + "related/main.jpg"}}}}
        html = f'<script type="application/json">{json.dumps(document)}</script>'
        groups = self.select(html, artsy=True)
        self.assertEqual(len(groups), 1)
        self.assertTrue(all("/target/" in u for u in groups[0].urls))

    def test_malformed_jsonld_does_not_abort_selection(self):
        html = '<script type="application/ld+json">[null, {"@type": 42}]</script><main><img src="/work.jpg"></main>'
        self.assertEqual(len(self.select(html)), 1)

    def test_artwork_gallery_beats_unrelated_social_card(self):
        html = '<meta property="og:image" content="/brand.jpg"><div data-test="artworkImage"><img src="' + CDN + 'target/large.jpg"></div>'
        group, = self.select(html, artsy=True)
        self.assertTrue(all('/target/' in url for url in group.urls))
        self.assertIn(CDN + 'target/normalized.jpg', group.urls)

    def test_article_image_beats_social_card_unrelated_to_content(self):
        group, = self.select('<meta property="og:image" content="/brand.jpg"><article><img src="/article.jpg"></article>')
        self.assertEqual(group.urls, ['https://www.artsy.net/article.jpg'])

    def test_old_unwanted_terms_do_not_discard_larger_source_images(self):
        config = ScraperConfig(unwanted_image_terms=["larger", "source", "logo"])
        soup = BeautifulSoup('<main><img src="/source/larger.jpg"></main>', "html.parser")
        self.assertEqual(len(select_image_groups(soup, PAGE, config)), 1)


if __name__ == "__main__":
    unittest.main()
