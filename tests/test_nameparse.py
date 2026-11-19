"""名称解析的边界：5 位截断时间、6 位完整时间、缺段不合规。"""

import unittest

from autorename.nameparse import parse_filename


class TruncatedTimeFragmentTest(unittest.TestCase):
    def test_five_digit_fragment_means_seconds_lost_their_leading_zero(self):
        """`11156` 是 11:15:06 —— 秒的个位单独一位，不能硬解 HHMMSS。"""
        parsed = parse_filename("82331647_TCSB218112026_11156.png")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.clock, "11:15:06")
        self.assertEqual(parsed.time_fragment, "11156")


class CompleteTimeFragmentTest(unittest.TestCase):
    def test_six_digit_fragment_parses_as_hhmmss(self):
        parsed = parse_filename("82331647_TCSB218112026_111024.png")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.clock, "11:10:24")
        self.assertEqual(parsed.time_fragment, "111024")


class ZeroDroppedFromMinutesTest(unittest.TestCase):
    def test_five_digit_fragment_can_also_mean_minutes_lost_their_zero(self):
        """实拍图里 `11835` 是 11:08:35（分钟丢了 0），不是 11:83:05。"""
        parsed = parse_filename("82331647_TCSB218112026_11835.png")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.clock, "11:08:35")


class MalformedNameTest(unittest.TestCase):
    def test_missing_time_segment_is_not_compliant(self):
        """缺段的名字返回 None，由调用方标「不合规」，不抛异常。"""
        self.assertIsNone(parse_filename("82331647_111024.png"))

    def test_too_short_time_fragment_is_not_compliant(self):
        """3 位、4 位不是「丢了一个 0」，是缺段：不能凑成 01:05:06 蒙混过关。"""
        self.assertIsNone(parse_filename("82331647_TCSB218112026_156.png"))
        self.assertIsNone(parse_filename("82331647_TCSB218112026_1115.png"))


if __name__ == "__main__":
    unittest.main()
