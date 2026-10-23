import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function createStory(page: Page) {
  await page.getByRole("button", { name: "New story", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Use fictional research example" })
    .click();
  await dialog
    .getByLabel("Working title")
    .fill("Research update " + Date.now());
  await dialog.getByRole("button", { name: "Prepare channel drafts" }).click();
  await expect(
    page.getByRole("tab", { name: "LinkedIn", exact: true }),
  ).toBeVisible({ timeout: 20000 });
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Open fictional demo workspace" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Content studio", exact: true }),
  ).toBeVisible();
});

test("connections show missing credentials and checks do not publish", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Publishing connections" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("API KEY MISSING");
  await dialog
    .getByRole("button", { name: "Check connections", exact: true })
    .click();
  await expect(dialog).toContainText("Add OPENAI_API_KEY");
  await expect(dialog).toContainText("Built-in destination is available.");
  const a11y = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(a11y.violations).toEqual([]);
});

test("retained JSON example imports into an editable source form", async ({
  page,
}) => {
  await page.getByRole("button", { name: "New story", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Import source file")
    .setInputFiles("../examples/urban-update.json");
  await expect(dialog.getByLabel("Working title")).toHaveValue(
    "Urban Futures: October workshop findings",
  );
  await expect(dialog.getByLabel("Source material")).toHaveValue(
    /48 residents/,
  );
  await dialog
    .getByLabel("Working title")
    .fill("Imported example under review");
  await dialog.getByRole("button", { name: "Prepare channel drafts" }).click();
  await expect(
    page.getByRole("tab", { name: "LinkedIn", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByRole("button", { name: "Approve & publish", exact: true }),
  ).toBeDisabled();
});

test("studio is accessible and mobile has no page overflow", async ({
  page,
}) => {
  const a11y = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(a11y.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "New story", exact: true }),
  ).toBeVisible();
});

test("source creates three editable previews and only explicit approval publishes", async ({
  page,
}) => {
  await createStory(page);
  await expect(
    page.getByRole("button", { name: "Approve & publish", exact: true }),
  ).toBeDisabled();
  await page.getByRole("tab", { name: "Website", exact: true }).click();
  await expect(page.locator(".website-preview h2")).toContainText(
    "Research update",
  );
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Draft", exact: true })
    .fill(
      "A reviewed announcement. The findings remain preliminary and require further community review.",
    );
  await page.getByRole("checkbox", { name: "Website Local test CMS" }).check();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve & publish", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("revision 2");
  await dialog
    .getByRole("button", { name: "Approve & publish", exact: true })
    .click();
  const results = page.locator(".editor-publications");
  await expect(results.getByText("Published", { exact: true })).toBeVisible({
    timeout: 25000,
  });
  const href = await results
    .getByRole("link", { name: "Open published article" })
    .getAttribute("href");
  const article = await page.request.get(href!);
  expect(article.status()).toBe(200);
  expect(await article.text()).toContain("A reviewed announcement.");
  await expect(results.locator(".publication-result")).toHaveCount(1);
});

test("partial failure can recover without republishing successful channels", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Publishing connections" }).click();
  await page
    .getByRole("button", { name: "Fail the next social request once" })
    .click();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await createStory(page);
  await page.getByRole("checkbox", { name: "Website Local test CMS" }).check();
  await page
    .getByRole("checkbox", { name: "LinkedIn Social publishing sandbox" })
    .check();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve & publish", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Approve & publish", exact: true })
    .click();
  const results = page.locator(".editor-publications");
  await expect(
    results.getByText("Needs attention", { exact: true }),
  ).toBeVisible({ timeout: 25000 });
  await expect(results.getByText("Published", { exact: true })).toBeVisible();
  const originalUrl = await results
    .getByRole("link", { name: "Open published article" })
    .getAttribute("href");
  await results.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(results.getByText("Published", { exact: true })).toHaveCount(2, {
    timeout: 25000,
  });
  expect(
    await results
      .getByRole("link", { name: "Open published article" })
      .getAttribute("href"),
  ).toBe(originalUrl);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Draft", exact: true })
    .fill("A new revision awaiting a fresh human approval.");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByText("Revision 3", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve & publish", exact: true }),
  ).toBeEnabled();
  await expect(results).not.toBeVisible();
});
