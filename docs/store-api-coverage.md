# Store API Coverage Matrix

This file tracks official-public-API coverage for App Store Connect, Google Play Android Publisher, Play Developer Reporting, and Play Console Cloud Storage report access.

Statuses: `typed-supported`, `generic-supported`, `planned`, `console-only`, `not-public`, `not-applicable`.

## Summary

- Total categories: 236
- console-only: 2
- generic-supported: 191
- typed-supported: 43

## Operation Registry

| Operation | Provider | Status | Exposure | Mutability | Confirmation |
| --- | --- | --- | --- | --- | --- |
| `store.api_coverage` | coverage | typed-supported | cli+mcp | read | False |
| `app_store.generic_request` | app_store | generic-supported | cli+mcp | write | True |
| `play.generic_android_publisher_request` | play_android_publisher | generic-supported | cli+mcp | write | True |
| `app_store.sales_report` | app_store | typed-supported | cli+mcp | read | False |
| `app_store.analytics_reports` | app_store | typed-supported | cli+mcp | write | False |
| `app_store.custom_product_pages` | app_store | typed-supported | cli+mcp | write | True |
| `app_store.product_page_experiments` | app_store | typed-supported | cli+mcp | write | True |
| `app_store.review_submissions` | app_store | typed-supported | cli+mcp | write | True |
| `app_store.listing_push` | app_store | typed-supported | mcp-only | write | True |
| `app_store.iap_subscriptions` | app_store | typed-supported | mcp-only | write | True |
| `play.reporting_apps` | play_reporting | typed-supported | cli+mcp | read | False |
| `play.vitals` | play_reporting | typed-supported | cli+mcp | read | False |
| `play.report_exports` | play_reports | typed-supported | cli+mcp | read | False |
| `play.listing_push` | play_android_publisher | typed-supported | mcp-only | write | True |
| `play.release_bundle` | play_android_publisher | typed-supported | mcp-only | write | True |
| `play.products_pricing` | play_android_publisher | typed-supported | mcp-only | write | True |

## API Categories

| Provider | Category | Status | Source | Notes |
| --- | --- | --- | --- | --- |
| app_store | `accessibilityDeclarations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `actors` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ageRatingDeclarations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionDomains` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionKeys` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionPackageDeltas` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionPackageVariants` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionPackageVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `alternativeDistributionPackages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `analyticsReportInstances` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `analyticsReportRequests` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `analyticsReportSegments` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `analyticsReports` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `androidToIosAppMappingDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appAvailabilities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appCategories` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipAdvancedExperienceImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipAdvancedExperiences` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipAppStoreReviewDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipDefaultExperienceLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipDefaultExperiences` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClipHeaderImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appClips` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appCustomProductPageLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appCustomProductPageVersions` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appCustomProductPages` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appEncryptionDeclarationDocuments` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appEncryptionDeclarations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appEventLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appEventScreenshots` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appEventVideoClips` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appEvents` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appInfoLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appInfos` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appPreviewSets` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appPreviews` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appPricePoints` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appPriceSchedules` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appScreenshotSets` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appScreenshots` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appStoreReviewAttachments` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreReviewDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreVersionExperimentTreatmentLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appStoreVersionExperimentTreatments` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appStoreVersionExperiments` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appStoreVersionLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appStoreVersionPhasedReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreVersionPromotions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreVersionReleaseRequests` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreVersionSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `appStoreVersions` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `appTags` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `apps` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssetUploadFiles` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssetVersionAppStoreReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssetVersionExternalBetaReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssetVersionInternalBetaReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssetVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `backgroundAssets` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaAppClipInvocationLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaAppClipInvocations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaAppLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaAppReviewDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaAppReviewSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaBuildLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaCrashLogs` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaFeedbackCrashSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaFeedbackScreenshotSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaGroups` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaLicenseAgreements` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaRecruitmentCriteria` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaRecruitmentCriterionOptions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaTesterInvitations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `betaTesters` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `buildBetaDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `buildBetaNotifications` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `buildBundles` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `buildUploadFiles` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `buildUploads` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `builds` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `bundleIdCapabilities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `bundleIds` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `certificates` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciArtifacts` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciBuildActions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciBuildRuns` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciIssues` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciMacOsVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciProducts` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciTestResults` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciWorkflows` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `ciXcodeVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `customerReviewResponses` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `customerReviews` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `devices` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `diagnosticSignatures` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `endAppAvailabilityPreOrders` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `endUserLicenseAgreements` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `financeReports` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAchievementImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAchievementLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAchievementReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAchievementVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAchievements` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterActivities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterActivityImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterActivityLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterActivityVersionReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterActivityVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterAppVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterChallengeImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterChallengeLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterChallengeVersionReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterChallengeVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterChallenges` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterEnabledVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterGroups` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardEntrySubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSetImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSetLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSetMemberLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSetReleases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSetVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardSets` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboardVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterLeaderboards` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterMatchmakingQueues` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterMatchmakingRuleSetTests` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterMatchmakingRuleSets` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterMatchmakingRules` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterMatchmakingTeams` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `gameCenterPlayerAchievementSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseAppStoreReviewScreenshots` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseAvailabilities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseContents` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `inAppPurchaseOfferCodeCustomCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseOfferCodeOneTimeUseCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchaseOfferCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchasePricePoints` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `inAppPurchasePriceSchedules` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `inAppPurchaseSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `inAppPurchases` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `marketplaceSearchDetails` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `marketplaceWebhooks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `merchantIds` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `nominations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `passTypeIds` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `preReleaseVersions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `profiles` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `promotedPurchases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `reviewSubmissionItems` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `reviewSubmissions` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `routingAppCoverages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `salesReports` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `sandboxTesters` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `sandboxTestersClearPurchaseHistoryRequest` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `scmGitReferences` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `scmProviders` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `scmPullRequests` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `scmRepositories` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionAppStoreReviewScreenshots` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionAvailabilities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionGracePeriods` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionGroupLocalizations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionGroupSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionGroups` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `subscriptionImages` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionIntroductoryOffers` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionLocalizations` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `subscriptionOfferCodeCustomCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionOfferCodeOneTimeUseCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionOfferCodes` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionPricePoints` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `subscriptionPrices` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `subscriptionPromotionalOffers` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptionSubmissions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `subscriptions` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `territories` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| app_store | `territoryAvailabilities` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `userInvitations` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `users` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `webhookDeliveries` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `webhookPings` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `webhooks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| app_store | `winBackOffers` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `applications` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `apprecovery` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.apks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.bundles` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.countryavailability` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.deobfuscationfiles` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.details` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.deviceTierConfigs` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.expansionfiles` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.generatedapks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.images` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.listings` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `edits.testers` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `edits.tracks` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `externaltransactions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `generatedapks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `grants` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `inappproducts` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `internalappsharingartifacts` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `monetization.onetimeproducts` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `monetization.onetimeproducts.purchaseOptions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `monetization.subscriptions` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_android_publisher | `monetization.subscriptions.basePlans` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `monetization.subscriptions.basePlans.offers` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `monetization.subscriptionsv2` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `orders` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `purchases.products` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `purchases.subscriptions` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `purchases.subscriptionsv2` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `purchases.voidedpurchases` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `reviews` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `systemapks` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `systemapks.variants` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `users` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_reporting | `anomalies` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_reporting | `apps` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_reporting | `vitals` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_reports | `objects` | typed-supported | official-api | Typed CLI/MCP workflow exists. |
| play_reports | `buckets` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_reports | `projects` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_reports | `objectAccessControls` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_reports | `bucketAccessControls` | generic-supported | official-api | Reachable through the provider generic official API request operation; typed workflow is not implemented yet. |
| play_android_publisher | `customStoreListings` | console-only | console-feature | Google Play Console supports custom store listings, but no public Android Publisher resource was found. |
| play_android_publisher | `storeListingExperiments` | console-only | console-feature | Google Play Console supports store listing experiments, but no public Android Publisher resource was found. |
