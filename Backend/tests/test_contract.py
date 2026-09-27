import unittest

from core.contract import _clean_time, normalize_chat, normalize_explanation, parse_json_object
from handles.documents import MAX_UPLOAD_BYTES, detect_media


class ContractTests(unittest.TestCase):
    def test_explanation_drops_unknown_schedule_fields(self):
        result = normalize_explanation(
            {
                "document_type": "Ordonnance",
                "summary": "Un antidouleur est indiqué.",
                "items": [{"title": "Paracétamol", "detail": "Nom lu sur l'ordonnance."}],
                "next_steps": ["Demandez confirmation au pharmacien."],
                "uncertainties": [],
                "emergency": {"detected": False, "message": "ignore me"},
                "medicines": [
                    {
                        "name": "Paracétamol",
                        "instructions": "Si besoin",
                        "dose": None,
                        "times": ["8:00", "25:99", "20h00", "8h"],
                        "duration_days": 0,
                    }
                ],
            },
            "fr",
        )
        medicine = result["medicines"][0]
        self.assertEqual(medicine["times"], ["08:00", "20:00"])
        self.assertEqual(_clean_time("8h"), "08:00")
        self.assertIsNone(_clean_time("soir"))
        self.assertNotIn("dose", medicine)
        self.assertNotIn("duration_days", medicine)
        self.assertEqual(result["emergency"], {"detected": False, "message": ""})
        self.assertLessEqual(MAX_UPLOAD_BYTES, 10 * 1024 * 1024)

    def test_invalid_times_become_an_uncertainty(self):
        result = normalize_explanation(
            {
                "summary": "Résumé",
                "items": [],
                "medicines": [{"name": "A", "instructions": "", "times": ["soir"]}],
                "emergency": {"detected": True, "message": ""},
            },
            "ary",
        )
        self.assertNotIn("times", result["medicines"][0])
        self.assertTrue(result["uncertainties"])
        self.assertTrue(result["emergency"]["detected"])
        self.assertTrue(result["emergency"]["message"])
        self.assertTrue(result["items"])
        self.assertTrue(result["next_steps"])

    def test_chat_requires_a_reply(self):
        parsed = normalize_chat(
            {"reply": "  Bonjour  ", "emergency": {"detected": False, "message": "x"}},
            "fr",
        )
        self.assertEqual(parsed["reply"], "Bonjour")
        self.assertEqual(parsed["emergency"]["message"], "")
        with self.assertRaises(ValueError):
            normalize_chat({"reply": "  "}, "fr")

    def test_json_fence_is_accepted(self):
        data = parse_json_object('```json\n{"reply": "ok"}\n```')
        self.assertEqual(data["reply"], "ok")

    def test_media_detection(self):
        self.assertEqual(detect_media("note.jpg", ""), "image/jpeg")
        self.assertEqual(detect_media("scan.pdf", "application/octet-stream"), "application/pdf")
        self.assertEqual(detect_media("photo", "image/jpg"), "image/jpeg")
        self.assertIsNone(detect_media("notes.txt", "text/plain"))


if __name__ == "__main__":
    unittest.main()
