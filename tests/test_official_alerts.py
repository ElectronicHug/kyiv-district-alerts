import unittest

from src.official_alerts import official_kyiv_alert_intro, official_kyiv_alert_state


class OfficialKyivAlertsTests(unittest.TestCase):
    def test_explicit_levels(self):
        self.assertEqual(official_kyiv_alert_state(
            "🟡 Жовтий рівень небезпеки\nОголошено повітряну тривогу через дронову загрозу."), "yellow")
        self.assertEqual(official_kyiv_alert_state(
            "🔴 Червоний рівень небезпеки\nОголошено повітряну тривогу через ракетну загрозу."), "red")
        self.assertEqual(official_kyiv_alert_state("🟢 Відбій повітряної тривоги."), "clear")
        self.assertEqual(official_kyiv_alert_state("🟢 м. Київ - відбій повітряної тривоги!"), "clear")

    def test_unrelated_post_is_not_a_status(self):
        self.assertIsNone(official_kyiv_alert_state("У Шевченківському районі пошкоджено будівлю."))
        self.assertIsNone(official_kyiv_alert_state("Сьогодні згадували червоний рівень небезпеки."))
        self.assertIn("Київ", official_kyiv_alert_intro("red"))


if __name__ == "__main__":
    unittest.main()
