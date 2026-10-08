# Node App (Book Management) – Troubleshooting Report

Seven bugs were found and fixed. Every backend fix has a regression test in `nodejs/tests/books.test.js`. Each of those tests fails on the original code and passes on the fixed code.

---

## 1. Category filter showed the wrong books

**File:** `src/repositories/bookRepository.js`

**Problem:** Choosing a category (e.g. "Science") showed every book *except* the Science ones. The SQL condition used "not equal":

```js
conditions.push("category != ?");
```

**Fix:** Use equality.

```js
conditions.push("category = ?");
```

---

## 2. `/api/books/search` was unreachable

**File:** `src/routes/books.js`

**Problem:** Express matches routes in the order they are registered. `GET /:id` came before `GET /search`, so for `/api/books/search` Express treated `"search"` as an `id`. The request went to `getById`, which returned **404 "Book not found"**. The search controller never ran.

```js
router.get("/:id", controller.getById);
router.get("/search", controller.search);
```

**Fix:** Register the specific route before the parameterised one.

```js
router.get("/search", controller.search);
router.get("/:id", controller.getById);
```

---

## 3. Decreasing stock actually increased it

**File:** `src/services/stockService.js`

**Problem:** For a negative adjustment, the code added the absolute value, so `-1` became `+1`. The "–" button increased stock, and the "Insufficient stock" check could never trigger.

```js
let next = book.quantity + delta;
if (delta < 0) {
  next = book.quantity + Math.abs(delta);
}
```

**Fix:** Just add the signed delta. A negative delta already subtracts.

```js
const next = book.quantity + delta;
```

---

## 4. Editing a book swapped price and published year

**File:** `src/controllers/bookController.js`

**Problem:** The service signature is
`updateBook(id, title, author, isbn, category, publishedYear, price, quantity)`,
but the controller passed `body.price` before `body.published_year`. Saving an edit either swapped the two values or failed validation with a 400 error (e.g. a price of `14.99` is not a valid year).

**Fix:** Pass the arguments in the order the service expects.

```js
body.category,
body.published_year,
body.price,
body.quantity
```

---

## 5. "Copies in stock" on the dashboard was too low

**File:** `src/repositories/statsRepository.js`

**Problem:** Only books with `quantity > 1` were counted, so every book with exactly one copy was left out of the total.

```sql
COALESCE(SUM(CASE WHEN quantity > 1 THEN quantity ELSE 0 END), 0)
```

**Fix:** Sum all quantities. Books with 0 copies add nothing anyway.

```sql
COALESCE(SUM(quantity), 0)
```

---

## 6. Search box was always one keystroke behind

**File:** `frontend/js/app.js`

**Problem:** The input handler sent the *previous* query and only then saved the new one:

```js
const query = pendingQuery;
pendingQuery = searchInput.value.trim();
loadBooks(query);
```

Typing "Dune" searched for "Dun". Clearing the box still searched for the last letter. Also, while typing quickly, a slow older response could arrive after a newer one and overwrite the correct results.

**Fix:** Search with the current input value. A request counter ignores responses that are no longer the latest.

```js
searchInput.addEventListener("input", () => {
  loadBooks();
});

async function loadBooks(query = searchInput.value.trim()) {
  const requestId = ++booksRequestId;
  // ...fetch...
  if (requestId !== booksRequestId) {
    return; // a newer request has started, drop this stale result
  }
  // ...render...
}
```

---

## 7. Save errors were hidden behind the dialog

**Files:** `frontend/index.html`, `frontend/js/app.js`

**Problem:** When saving failed (e.g. "ISBN already exists", "Published year is out of range"), the error went into the page's `#message` element. That element sits behind the open modal `<dialog>`, so the user saw nothing happen and didn't know why.

**Fix:** Added a `#form-message` element inside the dialog. Save errors are shown there, and the message is cleared each time the dialog opens.

---

## Testing

```powershell
cd nodejs
npm install
npm test
```

Result: **18/18 tests pass** (12 original + 6 new regression tests):

- decreases stock by one
- rejects a stock decrease below zero
- filters books by category
- searches books through the search endpoint
- updates a book keeping year and price in their fields
- counts every copy in stock
