import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER_PATH = REPO_ROOT / "ohou-today-deal" / "scripts" / "ohou_today_deal.py"

spec = importlib.util.spec_from_file_location("ohou_today_deal", HELPER_PATH)
ohou_today_deal = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["ohou_today_deal"] = ohou_today_deal
spec.loader.exec_module(ohou_today_deal)


def sample_payload():
    return {
        "pageProps": {
            "dehydratedState": {
                "queries": [
                    {
                        "state": {
                            "data": {
                                "feed": [
                                    {
                                        "title": "러그 특가",
                                        "startAt": "2026-05-17T15:00:00Z",
                                        "endAt": "2026-05-20T15:00:00Z",
                                        "type": "DEAL",
                                        "deal": {
                                            "id": "1215312",
                                            "name": "디아망 방수러그",
                                            "imageUrl": "https://example.com/rug.png",
                                            "isSoldOut": False,
                                            "price": {
                                                "representativeOriginalPrice": "41040",
                                                "representativeSellingPrice": "24800",
                                                "discountRate": "39",
                                            },
                                            "brand": {"name": "체고루루"},
                                            "badgeProperties": {"isFreeDelivery": True},
                                            "reviewStatistic": {"reviewCount": 7504, "reviewAverage": 4.8},
                                            "scrapInfo": {"scrapCount": 64757},
                                        },
                                        "salesStats": {"annualCumulativeSales": "1000"},
                                        "bestDiscountPrice": {
                                            "price": "21500",
                                            "discountRate": "47",
                                            "discountPlanDescription": "쿠폰 할인가",
                                        },
                                    },
                                    {
                                        "title": "식기 특가",
                                        "type": "DEAL",
                                        "deal": {
                                            "id": "4070154",
                                            "name": "식탁 위에 핀 꽃 bowl",
                                            "isSoldOut": False,
                                            "price": {
                                                "representativeOriginalPrice": "50000",
                                                "representativeSellingPrice": "50000",
                                                "discountRate": "0",
                                            },
                                            "brand": {"name": "미브래"},
                                            "badgeProperties": {"isFreeDelivery": False},
                                            "reviewStatistic": {"reviewCount": 0, "reviewAverage": 0},
                                        },
                                        "bestDiscountPrice": {"price": "43500", "discountRate": "13"},
                                    },
                                ]
                            }
                        }
                    }
                ]
            }
        }
    }


class OhouTodayDealTest(unittest.TestCase):
    def test_extract_deals_normalizes_public_today_deal_shape(self):
        deals = ohou_today_deal.extract_deals(sample_payload())

        self.assertEqual(len(deals), 2)
        first = deals[0]
        self.assertEqual(first.id, "1215312")
        self.assertEqual(first.title, "디아망 방수러그")
        self.assertEqual(first.brand, "체고루루")
        self.assertEqual(first.original_price, 41040)
        self.assertEqual(first.selling_price, 24800)
        self.assertEqual(first.best_price, 21500)
        self.assertEqual(first.best_discount_rate, 47)
        self.assertTrue(first.free_delivery)
        self.assertEqual(first.url, "https://ohou.se/productions/1215312/selling")

    def test_filter_and_sort_deals(self):
        deals = ohou_today_deal.extract_deals(sample_payload())

        filtered = ohou_today_deal.filter_deals(
            deals,
            query="러그",
            min_discount=40,
            free_delivery=True,
        )
        sorted_deals = ohou_today_deal.sort_deals(deals, "discount")

        self.assertEqual([deal.id for deal in filtered], ["1215312"])
        self.assertEqual([deal.id for deal in sorted_deals], ["1215312", "4070154"])

    def test_extract_next_data_accepts_html_script(self):
        html_doc = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(sample_payload(), ensure_ascii=False)
            + "</script></html>"
        )

        payload = ohou_today_deal.extract_next_data(html_doc)

        self.assertEqual(
            payload["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["feed"][0]["deal"]["id"],
            "1215312",
        )

    def test_cli_prints_json_from_html_file(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".html") as fixture:
            fixture.write(
                '<script id="__NEXT_DATA__" type="application/json">'
                + json.dumps(sample_payload(), ensure_ascii=False)
                + "</script>"
            )
            fixture.flush()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                ohou_today_deal.main(["list", "--html-file", fixture.name, "--limit", "1"])

        output = json.loads(stdout.getvalue())

        self.assertEqual(output["count"], 1)
        self.assertEqual(output["items"][0]["id"], "1215312")


if __name__ == "__main__":
    unittest.main()
