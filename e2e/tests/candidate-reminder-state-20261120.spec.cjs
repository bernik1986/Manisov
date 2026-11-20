const { test, expect } = require('@playwright/test');
const path = require('node:path');

const A = 900001;
const B = 900002;
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1QAAAAASUVORK5CYII=', 'base64');
const reminder = (candidateId = B, commentId = 9002) => ({
  comment_id: commentId, candidate_id: candidateId, candidate_name: 'SYNTHETIC',
  comment_text: 'STATE-REGRESSION', reminder_at: '2026-01-01T10:00:00Z',
});
const entry = page => page.locator('.candidate-document-intake > button').first();
const review = page => page.locator('dialog.intake-dialog');
const nav = page => page.getByTestId('candidate-section-nav');
const section = (page, id) => nav(page).locator(`[data-section-tab="${id}"]`).click();
const profileSave = page => page.locator('.detail-block--tab-panel .detail-block__body > button');
const card = id => ({
  candidate: { candidate_id: id, surname: id === A ? 'ALPHA' : 'BETA', first_name: 'SYNTHETIC', email: 'stored@example.invalid' },
  applications: [{ application_id: 12, position_applied_for: 'STORED-POSITION' }],
  documents: [{ document_id: 41, document_type: 'Custom record', document_number: 'STORED-ROW' }],
});

function delayedResponse() {
  let route;
  let done;
  return {
    get waiting() { return Boolean(route); },
    async hold(value) {
      route = value;
      await new Promise(resolve => { done = resolve; });
      return true;
    },
    async release(response) {
      await route.fulfill(response);
      done();
    },
  };
}

async function releaseAndRender(page, pending, url, response) {
  const finished = page.waitForResponse(url);
  await pending.release(response);
  await (await finished).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

test.beforeEach(async ({ context, baseURL }, testInfo) => {
  const dist = process.env.PW_STATE_DIST || (testInfo.config.metadata.offlineCandidateState
    ? path.resolve(__dirname, '../../generated/frontend-state-fixes-20261120/dist') : null);
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== baseURL) return route.abort();
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: { items: [] } });
    if (!dist) return route.continue();
    const file = url.pathname.startsWith('/assets/') ? url.pathname.slice(1) : 'index.html';
    return route.fulfill({ path: path.join(dist, file) });
  });
});

async function setup(page, { handler, waitForCard = true, focus = '', scanKind = 'document' } = {}) {
  const state = { reads: [], updates: [], saves: 0, saved: false, intakeReads: 0, reminders: [reminder()] };
  await page.addInitScript(() => {
    const claims = btoa(JSON.stringify({ sub: '1', sid: 'state-regression', exp: Math.floor(Date.now() / 1000) + 3600 }));
    localStorage.setItem('authToken', `test.${claims}.test`);
    localStorage.setItem('authUser', JSON.stringify({ user_id: 1, username: 'synthetic-state-test', role: 'recruiter' }));
  });
  await page.route('**/api/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (/^\/api\/candidates\/\d+$/.test(pathname)) {
      const id = Number(pathname.split('/').at(-1));
      if (request.method() === 'GET') state.reads.push(id);
      if (request.method() === 'PUT') state.updates.push({ id, payload: request.postDataJSON() });
    }
    if (handler && await handler(route, pathname, request, state)) return;
    if (/^\/api\/candidates\/\d+$/.test(pathname)) {
      if (request.method() === 'PUT') return route.fulfill({ json: {} });
      const payload = card(Number(pathname.split('/').at(-1)));
      if (state.saved) {
        if (scanKind === 'diploma') {
          payload.diplomas = [{ certificate_id: 43, certificate_type: 'COC', certificate_name_raw: 'COC_NAT',
            certificate_group: 'Diploma', certificate_number: 'SCANNED-NEW' }];
        } else {
          payload.documents.push({ document_id: 42, document_type: "Seaman's Book", document_number: 'SCANNED-NEW' });
          payload.attachments = [{ attachment_id: 88, source: 'document', description: 'document:42', file_name: 'saved-scan.pdf' }];
        }
      }
      return route.fulfill({ json: payload });
    }
    if (pathname.endsWith('/comment-reminders/due')) return route.fulfill({ json: { items: state.reminders } });
    if (/\/comment-reminders\/\d+\/dismiss$/.test(pathname)) {
      state.reminders = state.reminders.filter(item => item.comment_id !== Number(pathname.split('/').at(-2)));
      return route.fulfill({ json: {} });
    }
    if (pathname.endsWith('/document-intake/status')) return route.fulfill({ json: { enabled: true } });
    if (pathname.endsWith('/document-intake/submissions')) return route.fulfill({ json: { items: [], upload_enabled: true } });
    if (pathname.includes('/files/')) return route.fulfill({ contentType: 'image/png', body: PNG });
    if (pathname.endsWith('/save')) {
      state.saved = true;
      state.saves++;
      return route.fulfill({ json: { results: [{ file_ids: ['f'], status: 'saved' }] } });
    }
    if (pathname.endsWith('/document-intake')) {
      state.intakeReads++;
      return route.fulfill({ json: {
        candidate_name: 'Synthetic Candidate', existing: [],
        catalog: [{ key: `${scanKind}:test`, kind: scanKind, label: 'Synthetic scan', fields: ['number'] }],
        batches: [{ batch_id: 'batch', items: [{
          file_id: 'f', name: 'synthetic.png', content_type: 'image/png', type_key: `${scanKind}:test`,
          fields: { number: 'SCANNED-NEW' }, saved: state.saved, warnings: [],
        }] }],
      } });
    }
    return route.fulfill({ json: { items: [], companies: [], vessels: [] } });
  });
  await page.goto(`/candidates/${A}${focus ? `?focus=${focus}` : ''}`);
  if (waitForCard) {
    await expect(page.getByTestId('candidate-detail')).toBeVisible();
    await expect(entry(page)).toBeVisible();
  }
  return state;
}

async function switchToB(page) {
  await page.locator('.comment-reminder-open').click();
  await expect(page).toHaveURL(new RegExp(`/candidates/${B}`));
}

test('failed B load hides all candidate forms and retry only edits B', async ({ page }) => {
  let fail = true;
  const state = await setup(page, { handler: async (route, pathname, request) => {
    if (pathname === `/api/candidates/${B}` && request.method() === 'GET' && fail) {
      await route.fulfill({ status: 500, json: { detail: 'Synthetic load failure' } });
      return true;
    }
    return false;
  } });
  await switchToB(page);
  await expect(page.getByTestId('candidate-load-error')).toBeVisible();
  await expect(page.getByTestId('candidate-detail')).toHaveCount(0);
  await expect(page.getByLabel('Candidate ID', { exact: true })).toHaveCount(0);
  expect(state.updates).toEqual([]);
  fail = false;
  await page.getByTestId('candidate-load-error').getByRole('button').click();
  await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
  await nav(page).locator('button').first().click();
  await expect(page.getByLabel('Candidate ID', { exact: true })).toHaveValue(String(B));
  await profileSave(page).click();
  await expect.poll(() => state.updates.length).toBe(1);
  expect(state.updates[0]).toMatchObject({ id: B, payload: { surname: 'BETA' } });
});

for (const status of [200, 500]) {
  test(`late A profile save (${status}) cannot change B or start another A load`, async ({ page }) => {
    const pending = delayedResponse();
    const state = await setup(page, { handler: async (route, pathname, request) => {
      if (pathname === `/api/candidates/${A}` && request.method() === 'PUT') return pending.hold(route);
      return false;
    } });
    await page.getByLabel('ERP No', { exact: true }).fill('A-UNSAVED');
    await profileSave(page).click();
    await expect.poll(() => pending.waiting).toBe(true);
    const aReads = state.reads.filter(id => id === A).length;
    await switchToB(page);
    await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
    await releaseAndRender(page, pending, `**/api/candidates/${A}`, { status, json: {} });
    await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
    expect(state.reads.filter(id => id === A)).toHaveLength(aReads);
    await nav(page).locator('button').first().click();
    await expect(page.getByLabel('ERP No', { exact: true })).toHaveValue('');
    await profileSave(page).click();
    await expect.poll(() => state.updates.length).toBe(2);
    expect(state.updates[1]).toMatchObject({ id: B, payload: { surname: 'BETA' } });
    await expect(page.getByTestId('candidate-detail').locator('p.error')).toHaveCount(0);
  });
}

for (const status of [200, 500]) {
  test(`late A card load (${status}) cannot replace an already loaded B`, async ({ page }) => {
    const pending = delayedResponse();
    await setup(page, { waitForCard: false, handler: async (route, pathname, request) => {
      if (pathname === `/api/candidates/${A}` && request.method() === 'GET') return pending.hold(route);
      return false;
    } });
    await expect.poll(() => pending.waiting).toBe(true);
    await switchToB(page);
    await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
    await releaseAndRender(page, pending, `**/api/candidates/${A}`, { status, json: card(A) });
    await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
    await expect(page.getByTestId('candidate-load-error')).toHaveCount(0);
  });
}

test('a wrong-identity response fails closed', async ({ page }) => {
  await setup(page, { handler: async (route, pathname) => {
    if (pathname === `/api/candidates/${B}`) {
      await route.fulfill({ json: card(A) });
      return true;
    }
    return false;
  } });
  await switchToB(page);
  await expect(page.getByTestId('candidate-load-error')).toBeVisible();
  await expect(page.getByTestId('candidate-detail')).toHaveCount(0);
});

test('same-candidate focus changes preserve drafts without reloading the card', async ({ page }) => {
  const state = await setup(page, { handler: async (route, pathname) => {
    if (pathname.endsWith('/comment-reminders/due')) {
      await route.fulfill({ json: { items: [reminder(A)] } });
      return true;
    }
    return false;
  } });
  await page.getByLabel('ERP No', { exact: true }).fill('KEEP-SAME-CARD');
  const reads = state.reads.length;
  await page.locator('.comment-reminder-open').click();
  await expect(page).toHaveURL(/focus=comments/);
  await nav(page).locator('button').first().click();
  await expect(page.getByLabel('ERP No', { exact: true })).toHaveValue('KEEP-SAME-CARD');
  expect(state.reads).toHaveLength(reads);
});

test('scan approval refreshes records and attachments without discarding any other form drafts', async ({ page }) => {
  const state = await setup(page);
  await nav(page).locator('button').nth(1).click();
  await page.getByLabel('Email', { exact: true }).fill('unsaved@example.invalid');
  await section(page, 'recruitment');
  await page.getByLabel('Position Applied For', { exact: true }).fill('UNSAVED-POSITION');
  await section(page, 'comments');
  await page.locator('.candidate-comments-form textarea').fill('UNSAVED-COMMENT');
  await section(page, 'documents');
  await page.locator('.inline-form input').first().fill('UNSAVED-NEW-ROW');
  const editedRow = page.locator('[data-scan-target="document:41"]');
  await editedRow.locator('.row-actions-cell button').first().click();
  await editedRow.locator('input').nth(1).fill('UNSAVED-ROW-EDIT');
  await entry(page).click();
  await expect(review(page).locator('.intake-fields input').first()).toHaveValue('SCANNED-NEW');
  await review(page).locator('.intake-editor button').last().click();
  await expect.poll(() => state.saves).toBe(1);
  await expect.poll(() => state.intakeReads).toBe(2);
  await review(page).locator('.intake-header button').click();
  await expect(editedRow.locator('input').nth(1)).toHaveValue('UNSAVED-ROW-EDIT');
  await expect(page.locator('.inline-form input').first()).toHaveValue('UNSAVED-NEW-ROW');
  const savedRow = page.locator('[data-scan-target="document:42"]');
  await expect(savedRow.locator('input').nth(1)).toHaveValue('SCANNED-NEW');
  await expect(savedRow.locator('.scan-cell-toolbar button').first()).toBeVisible();
  await expect(savedRow.locator('.missing-scan-cell')).toHaveCount(0);
  await section(page, 'recruitment');
  await expect(page.getByLabel('Position Applied For', { exact: true })).toHaveValue('UNSAVED-POSITION');
  await section(page, 'comments');
  await expect(page.locator('.candidate-comments-form textarea')).toHaveValue('UNSAVED-COMMENT');
  await nav(page).locator('button').nth(1).click();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('unsaved@example.invalid');
  expect(state.updates).toEqual([]);
});

test('failed intake-only refresh preserves the card and unsaved profile', async ({ page }) => {
  const state = await setup(page, { handler: async (route, pathname, request, current) => {
    if (pathname === `/api/candidates/${A}` && request.method() === 'GET' && current.saved) {
      await route.fulfill({ status: 500, json: { detail: 'Synthetic refresh failure' } });
      return true;
    }
    return false;
  } });
  await nav(page).locator('button').nth(1).click();
  await page.getByLabel('Email', { exact: true }).fill('preserved@example.invalid');
  await entry(page).click();
  await review(page).locator('.intake-editor button').last().click();
  await expect(review(page).getByRole('alert')).toBeVisible();
  await review(page).locator('.intake-header button').click();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue('preserved@example.invalid');
  await expect(page.getByTestId('candidate-load-error')).toHaveCount(0);
  expect(state.saves).toBe(1);
  expect(state.updates).toEqual([]);
});

test('intake refresh cannot reapply old URL focus and unmount an unsaved contract', async ({ page }) => {
  const state = await setup(page, { focus: 'certificate:43', scanKind: 'diploma' });
  await section(page, 'contract');
  const airport = page.getByTestId('contract-section').getByLabel('Home airport', { exact: true });
  await airport.fill('UNSAVED-AIRPORT');
  await entry(page).click();
  await review(page).locator('.intake-editor button').last().click();
  await expect.poll(() => state.intakeReads).toBe(2);
  await review(page).locator('.intake-header button').click();
  await expect(airport).toBeVisible();
  await expect(airport).toHaveValue('UNSAVED-AIRPORT');
  await section(page, 'diplomas');
  await expect(page.locator('[data-scan-target="certificate:43"] input[value="SCANNED-NEW"]')).toHaveCount(1);
  expect(state.updates).toEqual([]);
});

test('late intake save cannot refresh the previous candidate after switching', async ({ page }) => {
  const pending = delayedResponse();
  const state = await setup(page, { handler: async (route, pathname) => {
    if (pathname.endsWith('/save')) return pending.hold(route);
    return false;
  } });
  await entry(page).click();
  await review(page).locator('.intake-editor button').last().click();
  await expect.poll(() => pending.waiting).toBe(true);
  await review(page).locator('.intake-header button').click();
  const aReads = state.reads.filter(id => id === A).length;
  await switchToB(page);
  await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
  // Intake aborts its HTTP request on unmount, so no browser response event is required.
  await pending.release({ json: { results: [{ file_ids: ['f'], status: 'saved' }] } });
  await expect(page.getByTestId('candidate-photo-panel')).toContainText('BETA SYNTHETIC');
  expect(state.reads.filter(id => id === A)).toHaveLength(aReads);
});

test('a delayed pre-dismissal poll cannot resurrect the dismissed reminder', async ({ page }) => {
  const pending = delayedResponse();
  let hold = false;
  const state = await setup(page, { handler: async (route, pathname) => {
    if (pathname.endsWith('/comment-reminders/due') && hold) {
      hold = false;
      return pending.hold(route);
    }
    return false;
  } });
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(1);
  hold = true;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => pending.waiting).toBe(true);
  await page.locator('.comment-reminder-close').click();
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(0);
  await releaseAndRender(page, pending, '**/api/comment-reminders/due', { json: { items: [reminder()] } });
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(0);
  state.reminders = [reminder(A, 9010)];
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(1);
});

test('older overlapping reminder snapshots cannot overwrite newer results', async ({ page }) => {
  const pending = delayedResponse();
  let hold = false;
  const state = await setup(page, { handler: async (route, pathname) => {
    if (pathname.endsWith('/comment-reminders/due') && hold) {
      hold = false;
      return pending.hold(route);
    }
    return false;
  } });
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(1);
  hold = true;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => pending.waiting).toBe(true);
  state.reminders = [];
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(0);
  await releaseAndRender(page, pending, '**/api/comment-reminders/due', { json: { items: [reminder()] } });
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(0);
});

test('failed dismissal keeps the reminder visible and allows retry', async ({ page }) => {
  let fail = true;
  await setup(page, { handler: async (route, pathname) => {
    if (pathname.endsWith('/dismiss') && fail) {
      fail = false;
      await route.fulfill({ status: 500, json: { detail: 'Synthetic dismiss failure' } });
      return true;
    }
    return false;
  } });
  await page.locator('.comment-reminder-close').click();
  await expect(page.getByTestId('comment-reminder-alert').locator('small')).toBeVisible();
  await expect(page.locator('.comment-reminder-close')).toBeEnabled();
  await page.locator('.comment-reminder-close').click();
  await expect(page.getByTestId('comment-reminder-alert')).toHaveCount(0);
});

for (const order of ['full-first', 'intake-first']) {
  test(`overlapping full and intake loads preserve both updates (${order})`, async ({ page }) => {
    const full = delayedResponse();
    const partial = delayedResponse();
    let deleted = false;
    const payload = saved => ({
      ...card(A),
      family_contacts: deleted ? [] : [{ family_contact_id: 75, full_name: 'SYNTHETIC-CONTACT' }],
      documents: [...card(A).documents, ...(saved
        ? [{ document_id: 42, document_type: "Seaman's Book", document_number: 'SCANNED-NEW' }] : [])],
    });
    const state = await setup(page, { handler: async (route, pathname, request, current) => {
      if (pathname.endsWith('/family-contacts/75') && request.method() === 'DELETE') {
        deleted = true;
        await route.fulfill({ json: {} });
        return true;
      }
      if (pathname === `/api/candidates/${A}` && request.method() === 'GET') {
        if (current.saved) return partial.hold(route);
        if (deleted) return full.hold(route);
        await route.fulfill({ json: payload(false) });
        return true;
      }
      return false;
    } });
    await section(page, 'family_contacts');
    page.on('dialog', dialog => dialog.accept());
    const contact = page.locator('tr').filter({ hasText: 'SYNTHETIC-CONTACT' });
    await contact.locator('button').last().click();
    await expect.poll(() => full.waiting).toBe(true);
    const olderPayload = payload(false);
    await entry(page).click();
    await review(page).locator('.intake-editor button').last().click();
    await expect.poll(() => partial.waiting).toBe(true);
    if (order === 'full-first') {
      await releaseAndRender(page, full, `**/api/candidates/${A}`, { json: olderPayload });
      await releaseAndRender(page, partial, `**/api/candidates/${A}`, { json: payload(true) });
    } else {
      await releaseAndRender(page, partial, `**/api/candidates/${A}`, { json: payload(true) });
      await releaseAndRender(page, full, `**/api/candidates/${A}`, { json: olderPayload });
    }
    await expect.poll(() => state.intakeReads).toBe(2);
    await review(page).locator('.intake-header button').click();
    await expect(contact).toHaveCount(0);
    await section(page, 'documents');
    await expect(page.locator('[data-scan-target="document:42"] input').nth(1)).toHaveValue('SCANNED-NEW');
  });
}

test('a newer full reload wins over a delayed intake response for the same records', async ({ page }) => {
  const partial = delayedResponse();
  let deleted = false;
  await setup(page, { handler: async (route, pathname, request, current) => {
    if (pathname.endsWith('/family-contacts/75') && request.method() === 'DELETE') {
      deleted = true;
      await route.fulfill({ json: {} });
      return true;
    }
    if (pathname === `/api/candidates/${A}` && request.method() === 'GET') {
      if (current.saved && !deleted) return partial.hold(route);
      await route.fulfill({ json: {
        ...card(A), family_contacts: deleted ? [] : [{ family_contact_id: 75, full_name: 'SYNTHETIC-CONTACT' }],
        documents: deleted ? [{ document_id: 42, document_type: "Seaman's Book", document_number: 'LATEST-FULL' }] : [],
      } });
      return true;
    }
    return false;
  } });
  await entry(page).click();
  await review(page).locator('.intake-editor button').last().click();
  await expect.poll(() => partial.waiting).toBe(true);
  await review(page).locator('.intake-header button').click();
  await section(page, 'family_contacts');
  page.on('dialog', dialog => dialog.accept());
  const contact = page.locator('tr').filter({ hasText: 'SYNTHETIC-CONTACT' });
  await contact.locator('button').last().click();
  await expect(contact).toHaveCount(0);
  await releaseAndRender(page, partial, `**/api/candidates/${A}`, { json: {
    ...card(A), documents: [{ document_id: 42, document_type: "Seaman's Book", document_number: 'OLDER-INTAKE' }],
  } });
  await section(page, 'documents');
  await expect(page.locator('[data-scan-target="document:42"] input').nth(1)).toHaveValue('LATEST-FULL');
});

for (const retry of ['refresh-button', 'reopen']) {
  test(`failed saved-card refresh is retried by ${retry} without resaving or losing profile edits`, async ({ page }) => {
    let fail = true;
    let refreshAttempts = 0;
    const state = await setup(page, { handler: async (route, pathname, request, current) => {
      if (pathname === `/api/candidates/${A}` && request.method() === 'GET' && current.saved) {
        refreshAttempts++;
        if (fail) {
          await route.fulfill({ status: 500, json: { detail: 'Synthetic transient card failure' } });
          return true;
        }
      }
      return false;
    } });
    await nav(page).locator('button').nth(1).click();
    await page.getByLabel('Email', { exact: true }).fill('keep-retry@example.invalid');
    await entry(page).click();
    await review(page).locator('.intake-editor button').last().click();
    await expect(review(page).getByRole('alert')).toBeVisible();
    const refreshButton = () => review(page).locator('.intake-controls').first()
      .locator('.intake-actions').first().locator('button').last();
    await refreshButton().click();
    await expect.poll(() => refreshAttempts).toBe(2);
    await expect(review(page).getByRole('alert')).toBeVisible();
    fail = false;
    if (retry === 'reopen') {
      await review(page).locator('.intake-header button').click();
      await entry(page).click();
    } else {
      await refreshButton().click();
    }
    await expect.poll(() => refreshAttempts).toBe(3);
    await expect.poll(() => state.intakeReads).toBe(2);
    await expect(review(page).getByRole('alert')).toHaveCount(0);
    await review(page).locator('.intake-header button').click();
    await expect(page.getByLabel('Email', { exact: true })).toHaveValue('keep-retry@example.invalid');
    await section(page, 'documents');
    await expect(page.locator('[data-scan-target="document:42"]')).toHaveCount(1);
    expect(state.saves).toBe(1);
    expect(state.updates).toEqual([]);
  });
}
