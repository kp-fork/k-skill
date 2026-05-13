# daiso-product-search

## 0.3.0

### Minor Changes

- af55f58: Restore actionable Daiso pickup answers when store pickup stock is blocked by adding a `selPkupStr`-backed `getStorePickupEligibility()` helper plus `pickupEligibility` field on `lookupStoreProductAvailability()`. When pickup stock returns `Unauthorized`, the package now reports whether the selected store is registered as a pickup-capable store for the product instead of only saying "unknown".

### Patch Changes

- e873308: Handle Daiso Mall pickup-stock Unauthorized responses as structured unavailable results, include pickup-stock retrieval and inventory states, and mark online-stock fallback as reference-only.

## 0.2.0

### Minor Changes

- 2352856: Publish the official Daiso Mall store and pickup-stock lookup package.
