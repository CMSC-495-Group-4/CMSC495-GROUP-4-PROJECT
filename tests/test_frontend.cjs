
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('static/app.js', 'utf8');

function loadApp() {
  const document = {
    readyState: 'loading',
    addEventListener() {},
    getElementById() { return null; }
  };

  const context = vm.createContext({
    document,
    console,
    AbortController,
    CustomEvent: class {},
    Event: class {}
  });

  vm.runInContext(source, context);
  return context;
}

test('validLocation accepts a valid campus building', () => {
  const context = loadApp();

  const result = vm.runInContext(
    `validLocation({
      id: 1,
      name: 'Library',
      accessible: true
    })`,
    context
  );

  assert.equal(result, true);
});

test('validLocation rejects an invalid building ID', () => {
  const context = loadApp();

  const result = vm.runInContext(
    `validLocation({
      id: -1,
      name: 'Library',
      accessible: true
    })`,
    context
  );

  assert.equal(result, false);
});

test('validateRoute accepts a valid route response', () => {
  const context = loadApp();

  assert.doesNotThrow(() => {
    vm.runInContext(`
      validateRoute({
        routeId: 'route-1',
        directions: [{
          stepNumber: 1,
          instruction: 'Walk to the library',
          distanceMeters: 100
        }],
        distanceMeters: 100,
        estimatedMinutes: 2,
        predictionSource: 'distance-based',
        accessible: true,
        timePeriod: 'morning'
      })
    `, context);
  });
});

test('validateRoute rejects a negative travel time', () => {
  const context = loadApp();

  assert.throws(() => {
    vm.runInContext(`
      validateRoute({
        routeId: 'route-1',
        directions: [{
          stepNumber: 1,
          instruction: 'Walk to the library',
          distanceMeters: 100
        }],
        distanceMeters: 100,
        estimatedMinutes: -5,
        predictionSource: 'distance-based',
        accessible: true,
        timePeriod: 'morning'
      })
    `, context);
  }, /invalid route response/);
});

test('validateRoute rejects an unsupported time period', () => {
  const context = loadApp();

  assert.throws(() => {
    vm.runInContext(`
      validateRoute({
        routeId: 'route-1',
        directions: [{
          stepNumber: 1,
          instruction: 'Walk to the library',
          distanceMeters: 100
        }],
        distanceMeters: 100,
        estimatedMinutes: 2,
        predictionSource: 'distance-based',
        accessible: true,
        timePeriod: 'night'
      })
    `, context);
  }, /invalid route response/);
});
