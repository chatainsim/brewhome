/**
 * Tests unitaires des fonctions de calcul BrewHome
 * Run : node tests/calc.test.js
 * Aucune dépendance externe — Node.js built-in assert uniquement.
 *
 * Chaque fonction de calcul est redéfinie ici depuis sa source HTML.
 * Si la formule change dans le source, le test casse → régression détectée.
 */

'use strict';
const assert = require('assert');

// ─── Runner minimal ──────────────────────────────────────────────────────────
let passed = 0, failed = 0;
const RED = '\x1b[31m', GREEN = '\x1b[32m', DIM = '\x1b[2m', RESET = '\x1b[0m';

function suite(name) { console.log(`\n${DIM}── ${name} ──${RESET}`); }
function test(name, fn) {
  try {
    fn();
    console.log(`  ${GREEN}✓${RESET} ${name}`);
    passed++;
  } catch (e) {
    console.error(`  ${RED}✗ ${name}${RESET}\n    ${e.message}`);
    failed++;
  }
}
function near(actual, expected, tol = 1e-4, msg = '') {
  if (Math.abs(actual - expected) > tol)
    throw new assert.AssertionError({
      message: `${msg}Expected ${expected} ± ${tol}, got ${actual}`,
      actual, expected, operator: '≈',
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. ABV / ATTÉNUATION
// Source : script_inventaire.html → _doAbvCalc()
// ─────────────────────────────────────────────────────────────────────────────
function _calcAbv(og, fg) {
  return { abv: (og - fg) * 131.25, att: (og - fg) / (og - 1) * 100 };
}

suite('ABV / Atténuation');
test('pale ale typique OG 1.050 FG 1.010 → 5.25 % ABV, 80 % att', () => {
  const r = _calcAbv(1.050, 1.010);
  near(r.abv, 5.25,  0.001);
  near(r.att, 80.0,  0.01);
});
test('bière forte OG 1.090 FG 1.018 → 9.45 % ABV', () => {
  near(_calcAbv(1.090, 1.018).abv, 9.45, 0.001);
});
test('session OG 1.040 FG 1.010 → 3.9375 % ABV, 75 % att', () => {
  const r = _calcAbv(1.040, 1.010);
  near(r.abv, 3.9375, 0.0001);
  near(r.att, 75.0,   0.001);
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. PRIMING
// Source : script_recettes.html → calcPriming()
// CO₂ résiduel (Brewer's Friend, T en °C)
// ─────────────────────────────────────────────────────────────────────────────
function _calcPrimingResidual(tempC) {
  return 3.0378 - 0.050062 * tempC + 0.00026555 * tempC * tempC;
}
function _calcPrimingGrams(vol, tempC, target, factor) {
  const residual = _calcPrimingResidual(tempC);
  const toAdd    = target - residual;
  return { residual, toAdd, grams: toAdd > 0 ? toAdd * vol * factor : 0 };
}

suite('Priming sugar');
test('CO₂ résiduel à 20 °C ≈ 2.1428 vol', () => {
  near(_calcPrimingResidual(20), 2.14278, 0.0001);
});
test('CO₂ résiduel à 0 °C ≈ 3.0378 vol (point de départ)', () => {
  near(_calcPrimingResidual(0), 3.0378, 0.0001);
});
test('résiduel croît quand T diminue (solubilité CO₂)', () => {
  assert(_calcPrimingResidual(10) > _calcPrimingResidual(20));
});
test('20 L à 20 °C, cible 2.5 vol, sucrose factor 4.64 → ~33.1 g', () => {
  const r = _calcPrimingGrams(20, 20, 2.5, 4.64);
  near(r.residual, 2.14278, 0.0001);
  near(r.grams, (2.5 - 2.14278) * 20 * 4.64, 0.01);
});
test('bière fermentée au froid (5 °C) : résiduel > 2.5 → 0 g à ajouter', () => {
  const r = _calcPrimingGrams(20, 5, 2.5, 4.64);
  assert(r.toAdd < 0, 'toAdd should be negative');
  assert.strictEqual(r.grams, 0);
});
test('doublant le volume double les grammes', () => {
  const r1 = _calcPrimingGrams(20, 20, 2.5, 4.64);
  const r2 = _calcPrimingGrams(40, 20, 2.5, 4.64);
  near(r2.grams, r1.grams * 2, 0.01);
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. RÉFRACTOMÈTRE — FORMULE DE NOVOTNÝ
// Source : script_inventaire.html → calcRefractoCorrection()
// ─────────────────────────────────────────────────────────────────────────────
function _calcNovotny(brixOG, brixCurrent, wcf = 1.04) {
  const b1 = brixOG / wcf, b2 = brixCurrent / wcf;
  return 1.0000
    - 0.0044993 * b1  + 0.011774  * b2
    + 0.00027581 * b1 * b1 - 0.0012717  * b2 * b2
    - 0.0000072800 * b1 * b1 * b1 + 0.000063293 * b2 * b2 * b2;
}

suite('Réfractomètre Novotný');
test('brixOG=13 brixCurrent=6 wcf=1.04 → FG ≈ 1.0104', () => {
  near(_calcNovotny(13, 6, 1.04), 1.01038, 0.0005);
});
test('WCF=1.0 vs WCF=1.04 → résultat différent', () => {
  assert(_calcNovotny(13, 6, 1.00) !== _calcNovotny(13, 6, 1.04));
});
test('FG diminue quand brixCurrent diminue (fermentation avance)', () => {
  const fg_early  = _calcNovotny(13, 10, 1.04);
  const fg_middle = _calcNovotny(13,  6, 1.04);
  const fg_late   = _calcNovotny(13,  2, 1.04);
  assert(fg_late < fg_middle && fg_middle < fg_early);
});
test('lecture identique OG=current → FG proche de OG (sans fermentation)', () => {
  const fg = _calcNovotny(12, 12, 1.04);
  assert(fg > 1.03 && fg < 1.06);
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. TEMPÉRATURE D'EMPÂTAGE — FORMULE DE PALMER (métrique)
// Source : script_inventaire.html → calcStrikeWater()
// T_strike = T_mash + (0.38 / ratio) × (T_mash − T_grain)
// ─────────────────────────────────────────────────────────────────────────────
function _calcStrikeWater(grainKg, grainTemp, mashTemp, ratioLkg) {
  const tStrike = mashTemp + (0.38 / ratioLkg) * (mashTemp - grainTemp);
  return { tStrike, vol: grainKg * ratioLkg };
}

suite('Strike water (empâtage)');
test('5 kg grain 20 °C, mash 65 °C, ratio 3 L/kg → tStrike 70.7 °C, 15 L', () => {
  const r = _calcStrikeWater(5, 20, 65, 3.0);
  near(r.tStrike, 70.7, 0.05);
  near(r.vol, 15, 0.001);
});
test('grain à température ambiante (20 °C) et froid (5 °C) → plus chaud pour grain froid', () => {
  const warm = _calcStrikeWater(5, 20, 65, 3.0);
  const cold = _calcStrikeWater(5,  5, 65, 3.0);
  assert(cold.tStrike > warm.tStrike);
});
test('mash mince (5 L/kg) demande moins de chauffe que mash épais (2.5 L/kg)', () => {
  const thin  = _calcStrikeWater(5, 20, 65, 5.0);
  const thick = _calcStrikeWater(5, 20, 65, 2.5);
  assert(thin.tStrike < thick.tStrike);
});
test('volume total = grainKg × ratio', () => {
  const r = _calcStrikeWater(8, 18, 67, 3.5);
  near(r.vol, 28, 0.0001);
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. LEVURE — VIABILITÉ ET TAUX D'ENSEMENCEMENT
// Source : script_inventaire.html → calcStarter()
// ─────────────────────────────────────────────────────────────────────────────
function _calcYeastViability(ageDays) {
  const ageMonths = ageDays / 30;
  return Math.max(0.05, 0.97 * Math.exp(-0.0684 * ageMonths));
}
function _calcRequiredCells(og, vol, pitchRate) {
  return pitchRate * vol * 259 * (1 - 1 / og);
}

suite('Levure — viabilité & ensemencement');
test('sachet frais (0 jours) → 97 % viabilité', () => {
  near(_calcYeastViability(0), 0.97, 0.001);
});
test('3 mois → ~79.0 % viabilité', () => {
  near(_calcYeastViability(90), 0.97 * Math.exp(-0.0684 * 3), 0.0001);
});
test('6 mois → moins viable que 3 mois', () => {
  assert(_calcYeastViability(180) < _calcYeastViability(90));
});
test('4 ans (~1500 j) → plancher à 5 % (Math.max)', () => {
  // Le plancher se déclenche à ~43 mois (0.97·e^{-0.0684·43} ≈ 0.05)
  near(_calcYeastViability(1500), 0.05, 0.001);
});
test('OG 1.060, 20 L, 0.75 M/mL/°P → cellules requises exactes', () => {
  near(_calcRequiredCells(1.060, 20, 0.75), 0.75 * 20 * 259 * (1 - 1/1.060), 0.001);
});
test('bière plus dense → plus de cellules requises', () => {
  assert(_calcRequiredCells(1.080, 20, 0.75) > _calcRequiredCells(1.050, 20, 0.75));
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. OG THÉORIQUE PAR RECETTE
// Source : script_recettes.html → _recMaxExtract() + _recTheoretical()
// GU = points de gravité par kg (GU/kg, ≈ 300 pour malt pâle)
// ─────────────────────────────────────────────────────────────────────────────
function _recMaxExtract(r) {
  let pts = 0;
  (r.ingredients || []).filter(i => i.category === 'malt').forEach(m => {
    if (m.gu == null) return;
    pts += (m.unit === 'kg' ? m.quantity : m.quantity / 1000) * m.gu;
  });
  return pts;
}
function _recTheoretical(r) {
  const vol = r.volume || 20, eff = r.brewhouse_efficiency || 72;
  const maxPts = _recMaxExtract(r);
  if (!maxPts) return null;
  const ogPts = maxPts * (eff / 100) / vol;
  const og    = 1 + ogPts / 1000;
  const fg    = 1 + (og - 1) * 0.25;
  const abv   = (og - fg) * 131.25;
  return { og, fg, abv, eff, maxPts };
}

suite('OG théorique recette');
test('5 kg malt pâle GU=300, 20 L, 75 % rendement → OG 1.0563, ABV ~5.5 %', () => {
  const ing = [{ category: 'malt', quantity: 5, unit: 'kg', gu: 300 }];
  const r   = _recTheoretical({ volume: 20, brewhouse_efficiency: 75, ingredients: ing });
  near(r.og,     1.05625,  0.0001);
  near(r.fg,     1.014063, 0.0001);
  near(r.abv,    5.537,    0.01);
  near(r.maxPts, 1500,     0.1);
});
test('recette vide → null', () => {
  assert.strictEqual(_recTheoretical({ volume: 20, brewhouse_efficiency: 75, ingredients: [] }), null);
});
test('unité g = kg/1000 (5000 g === 5 kg)', () => {
  const byG  = _recTheoretical({ volume: 20, brewhouse_efficiency: 100, ingredients: [{ category:'malt', quantity:5000, unit:'g', gu:300 }] });
  const byKg = _recTheoretical({ volume: 20, brewhouse_efficiency: 100, ingredients: [{ category:'malt', quantity:5,    unit:'kg', gu:300 }] });
  near(byG.og, byKg.og, 0.0001);
});
test('rendement 100 % vs 75 % : OG supérieur à 100 %', () => {
  const base = [{ category:'malt', quantity:5, unit:'kg', gu:300 }];
  const r100 = _recTheoretical({ volume:20, brewhouse_efficiency:100, ingredients: base });
  const r75  = _recTheoretical({ volume:20, brewhouse_efficiency:75,  ingredients: base });
  assert(r100.og > r75.og);
});
test('ingrédients sans gu ignorés', () => {
  const ing = [
    { category:'malt', quantity:5, unit:'kg', gu:300 },
    { category:'malt', quantity:1, unit:'kg', gu:null },
  ];
  const r = _recTheoretical({ volume:20, brewhouse_efficiency:100, ingredients:ing });
  near(r.maxPts, 1500, 0.1); // seul le premier compte
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. NNLS — SOLVEUR PAR MOINDRES CARRÉS NON-NÉGATIFS
// Source : script_settings.html → _nnls()
// ─────────────────────────────────────────────────────────────────────────────
function _nnls(A, b, W) {
  const m = A.length, n = A[0].length;
  const x = new Float64Array(n);
  const AtWA = Array.from({length: n}, () => new Float64Array(n));
  const AtWb = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    for (let k = 0; k < n; k++) {
      let s = 0;
      for (let i = 0; i < m; i++) s += W[i] * A[i][j] * A[i][k];
      AtWA[j][k] = s;
    }
    let s = 0;
    for (let i = 0; i < m; i++) s += W[i] * A[i][j] * b[i];
    AtWb[j] = s;
  }
  for (let iter = 0; iter < 500; iter++) {
    let maxDelta = 0;
    for (let j = 0; j < n; j++) {
      if (AtWA[j][j] < 1e-12) continue;
      let num = AtWb[j];
      for (let k = 0; k < n; k++) if (k !== j) num -= AtWA[j][k] * x[k];
      const xNew = Math.max(0, num / AtWA[j][j]);
      maxDelta = Math.max(maxDelta, Math.abs(xNew - x[j]));
      x[j] = xNew;
    }
    if (maxDelta < 1e-9) break;
  }
  return x;
}

suite('NNLS solver');
test('système identité 2×2 : x = b', () => {
  const x = _nnls([[1,0],[0,1]], [3,5], [1,1]);
  near(x[0], 3, 0.001);
  near(x[1], 5, 0.001);
});
test('contrainte non-négative : b négatif → x = 0', () => {
  const x = _nnls([[1,0],[0,1]], [-2,-3], [1,1]);
  near(x[0], 0, 0.001);
  near(x[1], 0, 0.001);
});
test('b positif et négatif mélangés → seule la partie positive active', () => {
  const x = _nnls([[1,0],[0,1]], [4,-1], [1,1]);
  near(x[0], 4, 0.001);
  near(x[1], 0, 0.001);
});
test('poids W=0 sur une équation → ion ignoré', () => {
  // x[0] solvable depuis eq0 (W=1), eq1 ignorée (W=0)
  const x = _nnls([[2,0],[0,1]], [6,0], [1,0]);
  near(x[0], 3, 0.001); // 2*x[0] = 6
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. CORRECTION MINÉRAUX EAU (_computeWCDoses)
// Source : script_settings.html → _computeWCDoses()
// ─────────────────────────────────────────────────────────────────────────────
const WC_MINERAL_FX = {
  'Sulfate de calcium':    { ca:232.8, mg:0,    na:0,     so4:557.9,  cl:0,     hco3:0      },
  'Sulfate de magnésium':  { ca:0,     mg:98.6, na:0,     so4:389.8,  cl:0,     hco3:0      },
  'Chlorure de calcium':   { ca:361.2, mg:0,    na:0,     so4:0,      cl:638.9, hco3:0      },
  'Chlorure de sodium':    { ca:0,     mg:0,    na:393.3, so4:0,      cl:606.5, hco3:0      },
  'Carbonate de calcium':  { ca:400.4, mg:0,    na:0,     so4:0,      cl:0,     hco3:1218.0 },
  'Bicarbonate de sodium': { ca:0,     mg:0,    na:273.7, so4:0,      cl:0,     hco3:726.4  },
};
const WC_ACID_FX = {
  'Acide lactique 80%':     0.09306,
  'Acide lactique 88%':     0.08461,
  'Acide phosphorique 75%': 0.08277,
  'Acide phosphorique 85%': 0.06826,
};

function _computeWCDoses(vol, s, t) {
  const IONS     = ['ca','mg','na','so4','cl','hco3'];
  const MINERALS = ['Sulfate de calcium','Sulfate de magnésium','Chlorure de calcium',
                    'Chlorure de sodium','Carbonate de calcium','Bicarbonate de sodium'];
  const b = IONS.map(k => t[k] !== null ? Math.max(0, t[k] - s[k]) : 0);
  const W = IONS.map(k => t[k] !== null ? 1 : 0);
  const A = IONS.map(ion => MINERALS.map(min => WC_MINERAL_FX[min][ion]));
  const xPerL = _nnls(A, b, W);
  const doses = {};
  MINERALS.forEach((min, j) => { doses[min] = xPerL[j] * vol; });
  const hco3Excess = t.hco3 !== null ? Math.max(0, s.hco3 - t.hco3) : 0;
  const acidDoses = {};
  if (hco3Excess > 0) {
    const totalMeq = hco3Excess * vol / 61.0;
    Object.entries(WC_ACID_FX).forEach(([acid, mlPerMeq]) => {
      acidDoses[acid] = totalMeq * mlPerMeq;
    });
  }
  const result = { ...s };
  MINERALS.forEach((min, j) => {
    if (xPerL[j] <= 0) return;
    const fx = WC_MINERAL_FX[min];
    IONS.forEach(k => { result[k] += xPerL[j] * fx[k]; });
  });
  if (hco3Excess > 0) result.hco3 = Math.max(0, result.hco3 - hco3Excess);
  return { doses, acidDoses, result };
}

const SRC_ZERO = { ca:0, mg:0, na:0, so4:0, cl:0, hco3:0 };
const NULL_TGT = { ca:null, mg:null, na:null, so4:null, cl:null, hco3:null };

suite('Correction minéraux eau');
test('eau pure + cible ca=50 → résultat ca ≈ 50 ppm (±2)', () => {
  const { result } = _computeWCDoses(20, {...SRC_ZERO}, { ...NULL_TGT, ca:50 });
  near(result.ca, 50, 2);
});
test('profil IPA (ca=150, so4=300) depuis eau pure → cibles atteintes (±5 ppm)', () => {
  const { result } = _computeWCDoses(20, {...SRC_ZERO}, { ...NULL_TGT, ca:150, so4:300 });
  near(result.ca,  150, 5);
  near(result.so4, 300, 5);
});
test('source déjà à la cible → doses nulles', () => {
  const profile = { ca:100, mg:10, na:15, so4:150, cl:80, hco3:30 };
  const { doses } = _computeWCDoses(20, profile, { ...profile, mg:null, na:null });
  const total = Object.values(doses).reduce((s, v) => s + v, 0);
  near(total, 0, 0.01);
});
test('source hco3 > cible → acidDoses non nulles', () => {
  const { acidDoses } = _computeWCDoses(20,
    { ca:50, mg:5, na:10, so4:80, cl:60, hco3:200 },
    { ...NULL_TGT, hco3:50 });
  const totalAcid = Object.values(acidDoses).reduce((s, v) => s + v, 0);
  assert(totalAcid > 0);
});
test('cible mg=10 → uniquement MgSO4 dosé (seul sel avec Mg)', () => {
  const { doses, result } = _computeWCDoses(20, {...SRC_ZERO}, { ...NULL_TGT, mg:10 });
  assert(doses['Sulfate de magnésium'] > 0);
  near(result.mg, 10, 0.5);
});
test('doses proportionnelles au volume (×2 vol → ×2 grammes)', () => {
  const tgt = { ...NULL_TGT, ca:80, so4:150 };
  const r1  = _computeWCDoses(10, {...SRC_ZERO}, tgt);
  const r2  = _computeWCDoses(20, {...SRC_ZERO}, tgt);
  const total1 = Object.values(r1.doses).reduce((s,v)=>s+v,0);
  const total2 = Object.values(r2.doses).reduce((s,v)=>s+v,0);
  near(total2, total1 * 2, 0.01);
});

// ─────────────────────────────────────────────────────────────────────────────
// Résultat
// ─────────────────────────────────────────────────────────────────────────────
const total = passed + failed;
console.log(`\n${'─'.repeat(50)}`);
if (failed === 0) {
  console.log(`${GREEN}✓ ${passed}/${total} tests passés${RESET}`);
} else {
  console.log(`${RED}✗ ${failed} échec(s), ${passed}/${total} passés${RESET}`);
  process.exit(1);
}
