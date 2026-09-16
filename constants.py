"""
Shared constants for the casino-checker pipeline.
=================================================
Single source of truth for signet definitions, dish keywords and allergen sets.
Imported by signet_classifier, pdf_extractor, consistency, casino_core and
casino_report — kept dependency-free to avoid import cycles.
"""

# Sachbezugswert for meals (updated annually, see KBV Gastronomie §7).
SACHBEZUGSWERT = 4.60

# Canonical signet order, shared across all modules.
SIGNET_ORDER = ['VEGAN', 'VEGETARISCH', 'SCHWEIN', 'SCHWEIN+RIND', 'RIND', 'GEFLÜGEL', 'FISCH']

# Signets denoting meat or fish (used for category cross-checks).
MEAT_FISH_SIGNETS = frozenset({'SCHWEIN', 'SCHWEIN+RIND', 'RIND', 'GEFLÜGEL', 'FISCH'})

# Signets that carry no dietary conflict semantics and are skipped in checks/stats.
NON_DIET_SIGNETS = frozenset({'UNKNOWN', 'NACHHALTIG'})

# Console icons per finding confidence level.
CONFIDENCE_ICONS = {'high': '🔴', 'medium': '🟡', 'low': '⚪'}

# -----------------------------------------------------------------------------
# Dish keywords per meat/fish signet.
# Order matters for suggestion priority: the first matching signet wins in
# signet_for_keyword() (SCHWEIN before GEFLÜGEL before FISCH before RIND).
# -----------------------------------------------------------------------------
SCHWEIN_KEYWORDS = ['schwein', 'speck', 'schinken', 'kasseler', 'bratwurst', 'bacon', 'pancetta',
                    'leberkäs', 'wiener würstchen', 'bockwurst', 'jagdwurst', 'mettwurst']
RIND_KEYWORDS = ['rind', 'beef', 'gulasch vom rind', 'rindfleisch']
GEFLÜGEL_KEYWORDS = ['pute', 'turkey', 'huhn', 'hähnchen', 'chicken', 'geflügel', 'ente', 'nuggets']
FISCH_KEYWORDS = ['fisch', 'lachs', 'seelachs', 'pangasius', 'forelle', 'thunfisch', 'kabeljau',
                  'dorsch', 'scholle', 'garnele', 'shrimp', 'matjes', 'hering', 'calamari', 'fischragout',
                  'hoki', 'wels', 'rotbarsch', 'seehecht', 'kap-seehecht', 'saibling', 'zander',
                  'barsch', 'heilbutt', 'dorade', 'wolfsbarsch', 'tono', 'tonno']

# Keyword → signet mapping. Suggestion priority follows insertion order.
SIGNET_KEYWORDS = {
    'SCHWEIN': SCHWEIN_KEYWORDS,
    'GEFLÜGEL': GEFLÜGEL_KEYWORDS,
    'FISCH': FISCH_KEYWORDS,
    'RIND': RIND_KEYWORDS,
}

# Dairy/animal-product keywords that conflict with a VEGAN signet.
VEGAN_CONFLICTS = ['joghurt', 'yoghurt', 'käse', 'cheese', 'sahne', 'butter', 'quark',
                   'schmand', 'gouda', 'mozzarella', 'parmesan', 'frischkäse', 'hirtenkäse',
                   'feta', 'honig', 'honey', 'mayo', 'mascarpone', 'crème fraîche',
                   'hartkäse', 'blauschimmelkäse', 'ziegenkäse']

# -----------------------------------------------------------------------------
# Allergen codes (as declared in the PDFs).
# -----------------------------------------------------------------------------
DAIRY_ALLERGENS = frozenset({'g', 'g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'g7'})
EGG_ALLERGENS = frozenset({'c'})
# Fisch (d), Krebstiere (b) und Weichtiere (n) sind tierische Allergene, die
# vegan UND vegetarisch ausschließen. Empfehlung daher FISCH-Signet.
MARINE_ALLERGENS = frozenset({'b', 'd', 'n'})
