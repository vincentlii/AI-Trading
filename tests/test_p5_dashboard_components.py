import unittest
from types import SimpleNamespace

from trading_system.dashboard import components


class FakeColumn:
    def __init__(self):
        self.metrics = []

    def metric(self, label, value, help=None):
        self.metrics.append((label, value, help))


class FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.captions = []
        self.columns_created = []
        self.expanders = []
        self.markdowns = []

    def caption(self, value):
        self.captions.append(value)

    def columns(self, count):
        columns = [FakeColumn() for _ in range(count)]
        self.columns_created.append(columns)
        return columns

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return FakeContext()

    def markdown(self, value, *, unsafe_allow_html=False):
        self.markdowns.append((value, unsafe_allow_html))


class P5DashboardComponentsTests(unittest.TestCase):
    def test_status_cards_use_safe_summary_defaults_for_old_snapshot(self):
        fake_st = FakeStreamlit()
        snapshot = SimpleNamespace(summary={"quality_failures": 0})

        components.render_summary_status_cards(
            fake_st,
            snapshot,
            (
                components.StatusCardSpec(
                    label="\u6570\u636e\u8d28\u91cf",
                    summary_key="quality_failures",
                    help_text="\u672c\u5730 DuckDB \u8d28\u91cf\u68c0\u67e5",
                ),
                components.StatusCardSpec(
                    label="\u6700\u7ec8\u4fe1\u53f7",
                    summary_key="approved_signals",
                    default=0,
                ),
            ),
        )

        labels = [column.metrics[0][0] for column in fake_st.columns_created[0]]
        values = [column.metrics[0][1] for column in fake_st.columns_created[0]]
        self.assertEqual(labels, ["\u6570\u636e\u8d28\u91cf", "\u6700\u7ec8\u4fe1\u53f7"])
        self.assertEqual(values, [0, 0])

    def test_section_header_and_read_only_notice_render_professional_light_html(self):
        fake_st = FakeStreamlit()

        components.render_section_header(
            fake_st,
            "\u4fe1\u53f7\u8bca\u65ad",
            "\u8868\u683c\u4e0b\u6c89\uff0c\u7ed3\u8bba\u4f18\u5148\uff0c\u660e\u7ec6\u53ef\u8ffd\u6eaf\u3002",
        )
        components.render_read_only_notice(fake_st)

        markup = "\n".join(item[0] for item in fake_st.markdowns)
        self.assertIn("p5-section-header", markup)
        self.assertIn("\u4fe1\u53f7\u8bca\u65ad", markup)
        self.assertIn("\u53ea\u8bfb\u770b\u677f", markup)
        self.assertIn("#ffffff", markup)

    def test_table_container_formats_cells_and_handles_empty_rows(self):
        fake_st = FakeStreamlit()

        components.render_table_container(
            fake_st,
            (
                {
                    "symbol": "BTC/USDT",
                    "reason_codes": ("volume_price:cooldown", "risk"),
                    "score": 1.23456789,
                    "missing": None,
                },
            ),
            trace_note="\u6765\u6e90\uff1aP5.2 \u8bca\u65ad snapshot",
        )
        components.render_table_container(fake_st, ())

        table_markup = fake_st.markdowns[0][0]
        self.assertIn("p5-table-wrap", table_markup)
        self.assertIn("BTC/USDT", table_markup)
        self.assertIn("volume_price:cooldown, risk", table_markup)
        self.assertIn("1.23457", table_markup)
        self.assertIn("\u6765\u6e90", table_markup)
        self.assertEqual(fake_st.captions, ["\u6682\u65e0\u6570\u636e"])

    def test_metric_notes_and_lazy_area_are_fake_streamlit_testable(self):
        fake_st = FakeStreamlit()
        calls = []

        components.render_metric_notes(
            fake_st,
            (
                ("\u8fd1\u671f 200 window", "\u7528\u4e8e\u8bca\u65ad\u53ef\u7528\u6027\uff0c\u4e0d\u4ee3\u66ff P4 \u5b8c\u6574\u56de\u6d4b\u3002"),
                ("Proposal", "\u53ea\u5c55\u793a\u961f\u5217\u72b6\u6001\uff0c\u4e0d\u81ea\u52a8\u5e94\u7528\u3002"),
            ),
        )
        components.render_lazy_area(
            fake_st,
            "\u52a0\u8f7d\u5b8c\u6574\u660e\u7ec6",
            lambda: calls.append("rendered"),
            expanded=False,
        )

        self.assertIn("\u6307\u6807\u8bf4\u660e", fake_st.markdowns[0][0])
        self.assertEqual(fake_st.expanders, [("\u52a0\u8f7d\u5b8c\u6574\u660e\u7ec6", False)])
        self.assertEqual(calls, ["rendered"])


if __name__ == "__main__":
    unittest.main()
