// Materials mirror MaterialType in agent_schemas/report.py
export const MATERIALS = [
  { id: "plastic_pet",    en: "PET Bottles",  ur: "پی ای ٹی بوتل", icon: "🧴" },
  { id: "plastic_hdpe",   en: "HDPE Plastic", ur: "ایچ ڈی پی ای",   icon: "🪣" },
  { id: "glass",          en: "Glass",        ur: "شیشہ",           icon: "🍾" },
  { id: "metal_aluminum", en: "Aluminum",     ur: "ایلومینیم",      icon: "🥫" },
  { id: "metal_steel",    en: "Steel / Iron", ur: "لوہا",           icon: "🔩" },
  { id: "cardboard",      en: "Cardboard",    ur: "گتہ",            icon: "📦" },
  { id: "mixed_paper",    en: "Paper",        ur: "کاغذ",           icon: "📄" },
  { id: "other",          en: "Other",        ur: "دیگر",           icon: "♻️" },
];

export const LOCATIONS = [
  "Cantt",
  "New Multan",
  "Gulgasht Colony",
  "Shah Rukn-e-Alam Colony",
  "Bosan Road",
];

export const materialLabel = (id) =>
  MATERIALS.find((m) => m.id === id) ?? { id, en: id, ur: "", icon: "♻️" };
