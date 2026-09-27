import type { Explanation, Language } from "../types";
export function demoExplanation(language: Language): Explanation {
  const fr = language === "fr";
  return {
    document_type: fr ? "Ordonnance fictive" : "وصفة تجريبية",
    summary: fr
      ? "Cet exemple montre comment une ordonnance devient plus facile à lire. Le traitement A est fictif : il sert uniquement à découvrir l’explication et le calendrier."
      : "هاد المثال كيوريك كيفاش الوصفة كتولي واضحة. العلاج A غير مثال للتجربة باش تكتاشف الشرح والبرنامج.",
    items: [
      {
        title: fr ? "Traitement A" : "العلاج A",
        detail: fr
          ? "Un médicament fictif, présenté avec ses instructions dans un langage simple."
          : "دوا خيالي، مع تعليمات مشروحة بكلام ساهل.",
      },
      {
        title: fr ? "Les horaires" : "الأوقات",
        detail: fr
          ? "Deux rappels par jour pendant 5 jours dans cet exemple. Vous choisirez les heures avant de créer le calendrier."
          : "فهاد المثال كاينين جوج تذكيرات فالنهار لمدة 5 أيام. غادي تختار الأوقات قبل ما تصاوب البرنامج.",
      },
    ],
    next_steps: fr
      ? [
          "Vérifiez les informations avec le document original.",
          "Préparez vos questions pour votre pharmacien.",
          "Créez un calendrier après avoir confirmé les instructions.",
        ]
      : [
          "راجع المعلومات مع الوصفة الأصلية.",
          "وجد الأسئلة ديالك للصيدلي.",
          "صاوب البرنامج من بعد ما تتأكد من التعليمات.",
        ],
    uncertainties: [
      fr
        ? "Document de démonstration. Aucune prescription réelle ni recommandation de traitement."
        : "وثيقة للتجربة فقط. ماشي وصفة حقيقية وماشي نصيحة علاجية.",
    ],
    emergency: { detected: false, message: "" },
    medicines: [
      {
        name: fr ? "Traitement A (exemple)" : "العلاج A (مثال)",
        dose: fr ? "1 unité fictive" : "وحدة خيالية",
        instructions: fr
          ? "Données fictives pour tester le calendrier uniquement."
          : "معلومات خيالية غير باش تجرب البرنامج.",
        times: ["08:00", "20:00"],
        duration_days: 5,
      },
    ],
  };
}
