/** @typedef {{ slug: string, title: string, emoji: string, ingredients: string[], steps: string[] }} Recipe */

const STORAGE_FAV = "recipe-box-favourites";
const STORAGE_CUSTOM = "recipe-box-custom-recipes";

/** @type {Recipe[]} */
const EMBEDDED_RECIPES = [
  {
    slug: "tomato-pasta",
    title: "Tomato Basil Pasta",
    emoji: "🍝",
    ingredients: [
      "400 g spaghetti",
      "6 ripe tomatoes",
      "3 cloves garlic",
      "Fresh basil leaves",
      "3 tbsp olive oil",
      "Salt and black pepper",
    ],
    steps: [
      "Boil salted water and cook spaghetti until al dente.",
      "Dice tomatoes and mince the garlic.",
      "Warm olive oil in a pan and cook garlic until fragrant.",
      "Add tomatoes and simmer for ten minutes.",
      "Toss pasta with the sauce and torn basil.",
      "Season and serve warm.",
    ],
  },
  {
    slug: "garden-salad",
    title: "Garden Crunch Salad",
    emoji: "🥗",
    ingredients: [
      "Mixed lettuce",
      "1 cucumber",
      "2 carrots",
      "Cherry tomatoes",
      "Lemon juice",
      "Olive oil",
    ],
    steps: [
      "Wash and dry all vegetables.",
      "Slice cucumber and shred carrots.",
      "Halve the cherry tomatoes.",
      "Combine greens and vegetables in a large bowl.",
      "Whisk lemon juice with olive oil and a pinch of salt.",
      "Pour dressing over salad and toss gently.",
    ],
  },
  {
    slug: "morning-oats",
    title: "Morning Oat Bowl",
    emoji: "🥣",
    ingredients: [
      "1 cup rolled oats",
      "2 cups milk or water",
      "1 banana",
      "Honey",
      "Pinch of cinnamon",
    ],
    steps: [
      "Simmer oats in milk for five minutes, stirring often.",
      "Slice the banana.",
      "Spoon oats into a bowl.",
      "Top with banana slices.",
      "Drizzle honey and dust with cinnamon.",
    ],
  },
  {
    slug: "bean-chili",
    title: "Weeknight Bean Chili",
    emoji: "🫘",
    ingredients: [
      "2 cans kidney beans",
      "1 onion",
      "1 bell pepper",
      "2 tbsp chili powder",
      "1 can crushed tomatoes",
      "Vegetable stock",
    ],
    steps: [
      "Dice onion and pepper.",
      "Sauté vegetables in a pot until soft.",
      "Stir in chili powder for one minute.",
      "Add tomatoes, beans, and enough stock to cover.",
      "Simmer for twenty five minutes.",
      "Taste and adjust seasoning before serving.",
    ],
  },
  {
    slug: "veggie-rice",
    title: "Colorful Veggie Rice",
    emoji: "🍚",
    ingredients: [
      "2 cups cooked rice",
      "1 cup peas",
      "1 red pepper",
      "2 eggs",
      "Soy sauce",
      "Sesame oil",
    ],
    steps: [
      "Dice the pepper into small cubes.",
      "Scramble eggs in a hot wok and set aside.",
      "Stir fry pepper and peas until tender.",
      "Add rice and break up any clumps.",
      "Return eggs, splash soy sauce and sesame oil.",
      "Mix well and serve from the wok.",
    ],
  },
  {
    slug: "herb-omelette",
    title: "Herb Filled Omelette",
    emoji: "🍳",
    ingredients: [
      "3 eggs",
      "Fresh parsley",
      "Fresh chives",
      "Butter",
      "Salt",
      "Grated cheese optional",
    ],
    steps: [
      "Beat eggs with a pinch of salt.",
      "Chop herbs finely.",
      "Melt butter in a nonstick pan over medium heat.",
      "Pour in eggs and let the base set.",
      "Scatter herbs and cheese on one half.",
      "Fold omelette and slide onto a plate.",
    ],
  },
  {
    slug: "lentil-soup",
    title: "Cozy Lentil Soup",
    emoji: "🍲",
    ingredients: [
      "1 cup red lentils",
      "1 carrot",
      "1 celery stalk",
      "1 liter vegetable stock",
      "Turmeric",
      "Cumin",
    ],
    steps: [
      "Rinse lentils until water runs clear.",
      "Chop carrot and celery into small pieces.",
      "Combine lentils, vegetables, and stock in a pot.",
      "Add turmeric and cumin.",
      "Simmer until lentils fall apart, about thirty minutes.",
      "Blend lightly if you prefer a smoother soup.",
    ],
  },
  {
    slug: "berry-smoothie",
    title: "Berry Yogurt Smoothie",
    emoji: "🥤",
    ingredients: [
      "1 cup frozen mixed berries",
      "1 cup plain yogurt",
      "Half a cup milk",
      "1 tbsp oats",
      "Honey to taste",
    ],
    steps: [
      "Add berries, yogurt, and milk to a blender.",
      "Drop in oats for extra body.",
      "Blend until smooth and purple.",
      "Taste and sweeten with honey if needed.",
      "Pour into a glass and drink right away.",
    ],
  },
];

/** @type {{ recipes: Recipe[], favourites: Set<string>, tab: "all" | "favourites", view: "list" | "detail" | "new", search: string, detailSlug: string | null }} */
const state = {
  recipes: [],
  favourites: new Set(),
  tab: "all",
  view: "list",
  search: "",
  detailSlug: null,
};

const root = document.getElementById("app");
if (!root) {
  throw new Error("Missing #app root");
}

function loadFavourites() {
  try {
    const raw = localStorage.getItem(STORAGE_FAV);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((s) => typeof s === "string"));
  } catch {
    return new Set();
  }
}

function saveFavourites() {
  localStorage.setItem(STORAGE_FAV, JSON.stringify([...state.favourites]));
}

function loadCustomRecipes() {
  try {
    const raw = localStorage.getItem(STORAGE_CUSTOM);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isRecipe);
  } catch {
    return [];
  }
}

function saveCustomRecipes(custom) {
  localStorage.setItem(STORAGE_CUSTOM, JSON.stringify(custom));
}

/** @param {unknown} value */
function isRecipe(value) {
  if (!value || typeof value !== "object") return false;
  const r = /** @type {Record<string, unknown>} */ (value);
  return (
    typeof r.slug === "string" &&
    typeof r.title === "string" &&
    typeof r.emoji === "string" &&
    Array.isArray(r.ingredients) &&
    Array.isArray(r.steps)
  );
}

async function loadBaseRecipes() {
  if (window.location.protocol === "file:") {
    return EMBEDDED_RECIPES.map((r) => ({ ...r }));
  }
  try {
    const res = await fetch("recipes.json");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.every(isRecipe)) {
        return data;
      }
    }
  } catch {
    /* use embedded */
  }
  return EMBEDDED_RECIPES.map((r) => ({ ...r }));
}

function slugify(title) {
  return title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48);
}

function uniqueSlug(base) {
  let slug = base || "recipe";
  let n = 1;
  const existing = new Set(state.recipes.map((r) => r.slug));
  while (existing.has(slug)) {
    slug = `${base}-${n}`;
    n += 1;
  }
  return slug;
}

/** @param {Recipe | undefined} recipe */
function recipeBySlug(recipe) {
  return state.recipes.find((r) => r.slug === recipe);
}

function parseLines(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function matchesSearch(recipe, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  if (recipe.title.toLowerCase().includes(q)) return true;
  return recipe.ingredients.some((ing) => ing.toLowerCase().includes(q));
}

function visibleRecipes() {
  let list = state.recipes;
  if (state.tab === "favourites") {
    list = list.filter((r) => state.favourites.has(r.slug));
  }
  if (state.search.trim()) {
    list = list.filter((r) => matchesSearch(r, state.search.trim()));
  }
  return list;
}

function setState(patch) {
  Object.assign(state, patch);
  render();
}

function render() {
  root.innerHTML = "";
  const header = document.createElement("header");
  header.className = "app-header";

  const title = document.createElement("h1");
  title.className = "app-title";
  title.textContent = "Recipe Box";
  header.appendChild(title);

  if (state.view === "list") {
    const searchWrap = document.createElement("div");
    searchWrap.className = "search-wrap";
    const search = document.createElement("input");
    search.type = "search";
    search.className = "search-input";
    search.placeholder = "Search title or ingredient";
    search.value = state.search;
    search.setAttribute("data-testid", "search-input");
    search.addEventListener("input", () => {
      state.search = search.value;
      renderListOnly();
    });
    searchWrap.appendChild(search);
    header.appendChild(searchWrap);
  }

  root.appendChild(header);

  if (state.view === "list") {
    renderListChrome();
    renderGrid();
    return;
  }
  if (state.view === "detail") {
    renderDetail();
    return;
  }
  renderNewForm();
}

function renderListOnly() {
  const grid = root.querySelector(".recipe-grid");
  if (!grid) {
    render();
    return;
  }
  grid.replaceWith(buildGrid());
}

function renderListChrome() {
  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";

  const tabs = document.createElement("div");
  tabs.className = "tabs";

  const tabAll = document.createElement("button");
  tabAll.type = "button";
  tabAll.className = "tab" + (state.tab === "all" ? " is-active" : "");
  tabAll.textContent = "All recipes";
  tabAll.setAttribute("data-testid", "tab-all");
  tabAll.addEventListener("click", () => setState({ tab: "all" }));

  const tabFav = document.createElement("button");
  tabFav.type = "button";
  tabFav.className = "tab" + (state.tab === "favourites" ? " is-active" : "");
  tabFav.textContent = "Favourites";
  tabFav.setAttribute("data-testid", "tab-favourites");
  tabFav.addEventListener("click", () => setState({ tab: "favourites" }));

  tabs.append(tabAll, tabFav);

  const newBtn = document.createElement("button");
  newBtn.type = "button";
  newBtn.className = "btn-primary";
  newBtn.textContent = "New recipe";
  newBtn.setAttribute("data-testid", "new-recipe-button");
  newBtn.addEventListener("click", () =>
    setState({ view: "new", detailSlug: null }),
  );

  toolbar.append(tabs, newBtn);
  root.appendChild(toolbar);
}

function buildGrid() {
  const grid = document.createElement("div");
  grid.className = "recipe-grid";
  const items = visibleRecipes();

  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent =
      state.tab === "favourites"
        ? "No favourites yet. Open a recipe and tap the heart."
        : "No recipes match your search.";
    grid.appendChild(empty);
    return grid;
  }

  for (const recipe of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "recipe-card";
    card.setAttribute("data-testid", `recipe-card-${recipe.slug}`);

    const emoji = document.createElement("span");
    emoji.className = "recipe-card-emoji";
    emoji.textContent = recipe.emoji;

    const name = document.createElement("h2");
    name.className = "recipe-card-title";
    name.textContent = recipe.title;

    const meta = document.createElement("p");
    meta.className = "recipe-card-meta";
    const fav = state.favourites.has(recipe.slug) ? " · Saved" : "";
    meta.textContent = `${recipe.ingredients.length} ingredients${fav}`;

    card.append(emoji, name, meta);
    card.addEventListener("click", () =>
      setState({ view: "detail", detailSlug: recipe.slug }),
    );
    grid.appendChild(card);
  }
  return grid;
}

function renderGrid() {
  root.appendChild(buildGrid());
}

function renderDetail() {
  const recipe = recipeBySlug(state.detailSlug ?? undefined);
  if (!recipe) {
    setState({ view: "list", detailSlug: null });
    return;
  }

  const panel = document.createElement("article");
  panel.className = "detail-panel";

  const head = document.createElement("div");
  head.className = "detail-header";
  const emoji = document.createElement("span");
  emoji.className = "detail-emoji";
  emoji.textContent = recipe.emoji;
  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = recipe.title;
  head.append(emoji, title);
  panel.appendChild(head);

  const actions = document.createElement("div");
  actions.className = "detail-actions";

  const back = document.createElement("button");
  back.type = "button";
  back.className = "btn-ghost";
  back.textContent = "Back to list";
  back.setAttribute("data-testid", "back-button");
  back.addEventListener("click", () =>
    setState({ view: "list", detailSlug: null }),
  );

  const fav = document.createElement("button");
  fav.type = "button";
  const isFav = state.favourites.has(recipe.slug);
  fav.className = "btn-favourite" + (isFav ? " is-on" : "");
  fav.textContent = isFav ? "Favourited" : "Add to favourites";
  fav.setAttribute("data-testid", "favourite-toggle");
  fav.addEventListener("click", () => {
    if (state.favourites.has(recipe.slug)) {
      state.favourites.delete(recipe.slug);
    } else {
      state.favourites.add(recipe.slug);
    }
    saveFavourites();
    render();
  });

  actions.append(back, fav);
  panel.appendChild(actions);

  const ingTitle = document.createElement("h3");
  ingTitle.className = "section-title";
  ingTitle.textContent = "Ingredients";
  panel.appendChild(ingTitle);

  const ingList = document.createElement("ul");
  ingList.className = "ingredient-list";
  for (const item of recipe.ingredients) {
    const li = document.createElement("li");
    li.textContent = item;
    ingList.appendChild(li);
  }
  panel.appendChild(ingList);

  const stepTitle = document.createElement("h3");
  stepTitle.className = "section-title";
  stepTitle.textContent = "Steps";
  panel.appendChild(stepTitle);

  const stepList = document.createElement("ol");
  stepList.className = "step-list";
  for (const step of recipe.steps) {
    const li = document.createElement("li");
    li.textContent = step;
    stepList.appendChild(li);
  }
  panel.appendChild(stepList);

  root.appendChild(panel);
}

function renderNewForm() {
  const panel = document.createElement("form");
  panel.className = "form-panel";
  panel.noValidate = true;

  const back = document.createElement("button");
  back.type = "button";
  back.className = "btn-ghost";
  back.textContent = "Back to list";
  back.setAttribute("data-testid", "back-button");
  back.addEventListener("click", () => setState({ view: "list" }));
  panel.appendChild(back);

  const titleLabel = document.createElement("label");
  titleLabel.textContent = "Title";
  titleLabel.setAttribute("for", "new-title");
  const titleInput = document.createElement("input");
  titleInput.id = "new-title";
  titleInput.required = true;
  titleInput.setAttribute("data-testid", "new-recipe-title");
  panel.append(titleLabel, titleInput);

  const ingLabel = document.createElement("label");
  ingLabel.textContent = "Ingredients (one per line)";
  ingLabel.setAttribute("for", "new-ing");
  const ingInput = document.createElement("textarea");
  ingInput.id = "new-ing";
  ingInput.required = true;
  ingInput.setAttribute("data-testid", "new-recipe-ingredients");
  panel.append(ingLabel, ingInput);

  const stepLabel = document.createElement("label");
  stepLabel.textContent = "Steps (one per line)";
  stepLabel.setAttribute("for", "new-steps");
  const stepInput = document.createElement("textarea");
  stepInput.id = "new-steps";
  stepInput.required = true;
  stepInput.setAttribute("data-testid", "new-recipe-steps");
  panel.append(stepLabel, stepInput);

  const hint = document.createElement("p");
  hint.className = "form-hint";
  hint.textContent = "New recipes stay in this browser only.";
  panel.appendChild(hint);

  const save = document.createElement("button");
  save.type = "submit";
  save.className = "btn-primary";
  save.textContent = "Save recipe";
  save.setAttribute("data-testid", "new-recipe-save");
  panel.appendChild(save);

  panel.addEventListener("submit", (event) => {
    event.preventDefault();
    const title = titleInput.value.trim();
    const ingredients = parseLines(ingInput.value);
    const steps = parseLines(stepInput.value);
    if (!title || ingredients.length === 0 || steps.length === 0) {
      return;
    }
    const baseSlug = slugify(title);
    const slug = uniqueSlug(baseSlug);
    const recipe = {
      slug,
      title,
      emoji: "📝",
      ingredients,
      steps,
    };
    const custom = loadCustomRecipes();
    custom.push(recipe);
    saveCustomRecipes(custom);
    state.recipes = [...state.recipes, recipe];
    setState({ view: "detail", detailSlug: slug });
  });

  root.appendChild(panel);
}

async function init() {
  state.favourites = loadFavourites();
  const base = await loadBaseRecipes();
  const custom = loadCustomRecipes();
  const slugs = new Set(base.map((r) => r.slug));
  const merged = [...base];
  for (const c of custom) {
    if (!slugs.has(c.slug)) {
      merged.push(c);
      slugs.add(c.slug);
    }
  }
  state.recipes = merged;
  render();
}

init();
