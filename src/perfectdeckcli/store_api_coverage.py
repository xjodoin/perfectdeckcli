"""Official store API coverage inventory and markdown renderer."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from .store_operations import STORE_OPERATIONS, CoverageStatus, Provider


CategorySource = Literal["official-api", "console-feature"]


@dataclass(frozen=True)
class ApiCoverageEntry:
    provider: Provider
    category: str
    status: CoverageStatus
    source: CategorySource = "official-api"
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


APPLE_TYPED = frozenset({
    "analyticsReportInstances",
    "analyticsReportRequests",
    "analyticsReportSegments",
    "analyticsReports",
    "appCustomProductPageLocalizations",
    "appCustomProductPageVersions",
    "appCustomProductPages",
    "appInfoLocalizations",
    "appInfos",
    "appPreviewSets",
    "appPreviews",
    "appScreenshotSets",
    "appScreenshots",
    "appStoreVersionExperimentTreatmentLocalizations",
    "appStoreVersionExperimentTreatments",
    "appStoreVersionExperiments",
    "appStoreVersionLocalizations",
    "appStoreVersions",
    "inAppPurchaseLocalizations",
    "inAppPurchasePricePoints",
    "inAppPurchasePriceSchedules",
    "inAppPurchases",
    "reviewSubmissionItems",
    "reviewSubmissions",
    "salesReports",
    "subscriptionAvailabilities",
    "subscriptionGroups",
    "subscriptionLocalizations",
    "subscriptionPricePoints",
    "subscriptionPrices",
    "subscriptions",
    "territories",
})

APPLE_CATEGORIES = (
    "accessibilityDeclarations",
    "actors",
    "ageRatingDeclarations",
    "alternativeDistributionDomains",
    "alternativeDistributionKeys",
    "alternativeDistributionPackageDeltas",
    "alternativeDistributionPackageVariants",
    "alternativeDistributionPackageVersions",
    "alternativeDistributionPackages",
    "analyticsReportInstances",
    "analyticsReportRequests",
    "analyticsReportSegments",
    "analyticsReports",
    "androidToIosAppMappingDetails",
    "appAvailabilities",
    "appCategories",
    "appClipAdvancedExperienceImages",
    "appClipAdvancedExperiences",
    "appClipAppStoreReviewDetails",
    "appClipDefaultExperienceLocalizations",
    "appClipDefaultExperiences",
    "appClipHeaderImages",
    "appClips",
    "appCustomProductPageLocalizations",
    "appCustomProductPageVersions",
    "appCustomProductPages",
    "appEncryptionDeclarationDocuments",
    "appEncryptionDeclarations",
    "appEventLocalizations",
    "appEventScreenshots",
    "appEventVideoClips",
    "appEvents",
    "appInfoLocalizations",
    "appInfos",
    "appPreviewSets",
    "appPreviews",
    "appPricePoints",
    "appPriceSchedules",
    "appScreenshotSets",
    "appScreenshots",
    "appStoreReviewAttachments",
    "appStoreReviewDetails",
    "appStoreVersionExperimentTreatmentLocalizations",
    "appStoreVersionExperimentTreatments",
    "appStoreVersionExperiments",
    "appStoreVersionLocalizations",
    "appStoreVersionPhasedReleases",
    "appStoreVersionPromotions",
    "appStoreVersionReleaseRequests",
    "appStoreVersionSubmissions",
    "appStoreVersions",
    "appTags",
    "apps",
    "backgroundAssetUploadFiles",
    "backgroundAssetVersionAppStoreReleases",
    "backgroundAssetVersionExternalBetaReleases",
    "backgroundAssetVersionInternalBetaReleases",
    "backgroundAssetVersions",
    "backgroundAssets",
    "betaAppClipInvocationLocalizations",
    "betaAppClipInvocations",
    "betaAppLocalizations",
    "betaAppReviewDetails",
    "betaAppReviewSubmissions",
    "betaBuildLocalizations",
    "betaCrashLogs",
    "betaFeedbackCrashSubmissions",
    "betaFeedbackScreenshotSubmissions",
    "betaGroups",
    "betaLicenseAgreements",
    "betaRecruitmentCriteria",
    "betaRecruitmentCriterionOptions",
    "betaTesterInvitations",
    "betaTesters",
    "buildBetaDetails",
    "buildBetaNotifications",
    "buildBundles",
    "buildUploadFiles",
    "buildUploads",
    "builds",
    "bundleIdCapabilities",
    "bundleIds",
    "certificates",
    "ciArtifacts",
    "ciBuildActions",
    "ciBuildRuns",
    "ciIssues",
    "ciMacOsVersions",
    "ciProducts",
    "ciTestResults",
    "ciWorkflows",
    "ciXcodeVersions",
    "customerReviewResponses",
    "customerReviews",
    "devices",
    "diagnosticSignatures",
    "endAppAvailabilityPreOrders",
    "endUserLicenseAgreements",
    "financeReports",
    "gameCenterAchievementImages",
    "gameCenterAchievementLocalizations",
    "gameCenterAchievementReleases",
    "gameCenterAchievementVersions",
    "gameCenterAchievements",
    "gameCenterActivities",
    "gameCenterActivityImages",
    "gameCenterActivityLocalizations",
    "gameCenterActivityVersionReleases",
    "gameCenterActivityVersions",
    "gameCenterAppVersions",
    "gameCenterChallengeImages",
    "gameCenterChallengeLocalizations",
    "gameCenterChallengeVersionReleases",
    "gameCenterChallengeVersions",
    "gameCenterChallenges",
    "gameCenterDetails",
    "gameCenterEnabledVersions",
    "gameCenterGroups",
    "gameCenterLeaderboardEntrySubmissions",
    "gameCenterLeaderboardImages",
    "gameCenterLeaderboardLocalizations",
    "gameCenterLeaderboardReleases",
    "gameCenterLeaderboardSetImages",
    "gameCenterLeaderboardSetLocalizations",
    "gameCenterLeaderboardSetMemberLocalizations",
    "gameCenterLeaderboardSetReleases",
    "gameCenterLeaderboardSetVersions",
    "gameCenterLeaderboardSets",
    "gameCenterLeaderboardVersions",
    "gameCenterLeaderboards",
    "gameCenterMatchmakingQueues",
    "gameCenterMatchmakingRuleSetTests",
    "gameCenterMatchmakingRuleSets",
    "gameCenterMatchmakingRules",
    "gameCenterMatchmakingTeams",
    "gameCenterPlayerAchievementSubmissions",
    "inAppPurchaseAppStoreReviewScreenshots",
    "inAppPurchaseAvailabilities",
    "inAppPurchaseContents",
    "inAppPurchaseImages",
    "inAppPurchaseLocalizations",
    "inAppPurchaseOfferCodeCustomCodes",
    "inAppPurchaseOfferCodeOneTimeUseCodes",
    "inAppPurchaseOfferCodes",
    "inAppPurchasePricePoints",
    "inAppPurchasePriceSchedules",
    "inAppPurchaseSubmissions",
    "inAppPurchases",
    "marketplaceSearchDetails",
    "marketplaceWebhooks",
    "merchantIds",
    "nominations",
    "passTypeIds",
    "preReleaseVersions",
    "profiles",
    "promotedPurchases",
    "reviewSubmissionItems",
    "reviewSubmissions",
    "routingAppCoverages",
    "salesReports",
    "sandboxTesters",
    "sandboxTestersClearPurchaseHistoryRequest",
    "scmGitReferences",
    "scmProviders",
    "scmPullRequests",
    "scmRepositories",
    "subscriptionAppStoreReviewScreenshots",
    "subscriptionAvailabilities",
    "subscriptionGracePeriods",
    "subscriptionGroupLocalizations",
    "subscriptionGroupSubmissions",
    "subscriptionGroups",
    "subscriptionImages",
    "subscriptionIntroductoryOffers",
    "subscriptionLocalizations",
    "subscriptionOfferCodeCustomCodes",
    "subscriptionOfferCodeOneTimeUseCodes",
    "subscriptionOfferCodes",
    "subscriptionPricePoints",
    "subscriptionPrices",
    "subscriptionPromotionalOffers",
    "subscriptionSubmissions",
    "subscriptions",
    "territories",
    "territoryAvailabilities",
    "userInvitations",
    "users",
    "webhookDeliveries",
    "webhookPings",
    "webhooks",
    "winBackOffers",
)

PLAY_ANDROID_TYPED = frozenset({
    "edits",
    "edits.details",
    "edits.images",
    "edits.listings",
    "edits.tracks",
    "edits.bundles",
    "edits.deobfuscationfiles",
    "inappproducts",
    "monetization.subscriptions",
    "monetization.subscriptions.basePlans",
})

PLAY_ANDROID_CATEGORIES = (
    "applications",
    "apprecovery",
    "edits",
    "edits.apks",
    "edits.bundles",
    "edits.countryavailability",
    "edits.deobfuscationfiles",
    "edits.details",
    "edits.deviceTierConfigs",
    "edits.expansionfiles",
    "edits.generatedapks",
    "edits.images",
    "edits.listings",
    "edits.testers",
    "edits.tracks",
    "externaltransactions",
    "generatedapks",
    "grants",
    "inappproducts",
    "internalappsharingartifacts",
    "monetization.onetimeproducts",
    "monetization.onetimeproducts.purchaseOptions",
    "monetization.subscriptions",
    "monetization.subscriptions.basePlans",
    "monetization.subscriptions.basePlans.offers",
    "monetization.subscriptionsv2",
    "orders",
    "purchases.products",
    "purchases.subscriptions",
    "purchases.subscriptionsv2",
    "purchases.voidedpurchases",
    "reviews",
    "systemapks",
    "systemapks.variants",
    "users",
)

PLAY_REPORTING_TYPED = frozenset({"apps", "vitals"})
PLAY_REPORTING_CATEGORIES = ("anomalies", "apps", "vitals")

PLAY_REPORTS_TYPED = frozenset({"objects"})
PLAY_REPORTS_CATEGORIES = (
    "objects",
    "buckets",
    "projects",
    "objectAccessControls",
    "bucketAccessControls",
)

CONSOLE_ONLY = (
    ApiCoverageEntry(
        "play_android_publisher",
        "customStoreListings",
        "console-only",
        "console-feature",
        "Google Play Console supports custom store listings, but no public Android Publisher resource was found.",
    ),
    ApiCoverageEntry(
        "play_android_publisher",
        "storeListingExperiments",
        "console-only",
        "console-feature",
        "Google Play Console supports store listing experiments, but no public Android Publisher resource was found.",
    ),
)


def _entry(provider: Provider, category: str, typed: frozenset[str], *, notes: str = "") -> ApiCoverageEntry:
    if category in typed:
        return ApiCoverageEntry(provider, category, "typed-supported", notes=notes or "Typed CLI/MCP workflow exists.")
    return ApiCoverageEntry(
        provider,
        category,
        "generic-supported",
        notes=notes or "Reachable through the provider generic official API request operation; typed workflow is not implemented yet.",
    )


def list_api_coverage(provider: str | None = None) -> list[dict[str, str]]:
    """Return the current official store API category coverage matrix."""
    entries: list[ApiCoverageEntry] = []
    entries.extend(_entry("app_store", category, APPLE_TYPED) for category in APPLE_CATEGORIES)
    entries.extend(_entry("play_android_publisher", category, PLAY_ANDROID_TYPED) for category in PLAY_ANDROID_CATEGORIES)
    entries.extend(_entry("play_reporting", category, PLAY_REPORTING_TYPED) for category in PLAY_REPORTING_CATEGORIES)
    entries.extend(_entry("play_reports", category, PLAY_REPORTS_TYPED) for category in PLAY_REPORTS_CATEGORIES)
    entries.extend(CONSOLE_ONLY)
    if provider:
        entries = [entry for entry in entries if entry.provider == provider]
    return [entry.to_dict() for entry in entries]


def coverage_summary(provider: str | None = None) -> dict[str, object]:
    rows = list_api_coverage(provider)
    by_status = Counter(row["status"] for row in rows)
    by_provider = Counter(row["provider"] for row in rows)
    return {
        "total": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_provider": dict(sorted(by_provider.items())),
        "operations": [operation.to_dict() for operation in STORE_OPERATIONS],
    }


def render_coverage_markdown(provider: str | None = None) -> str:
    rows = list_api_coverage(provider)
    summary = coverage_summary(provider)
    lines = [
        "# Store API Coverage Matrix",
        "",
        "This file tracks official-public-API coverage for App Store Connect, Google Play Android Publisher, "
        "Play Developer Reporting, and Play Console Cloud Storage report access.",
        "",
        "Statuses: `typed-supported`, `generic-supported`, `planned`, `console-only`, `not-public`, `not-applicable`.",
        "",
        "## Summary",
        "",
        f"- Total categories: {summary['total']}",
    ]
    for status, count in summary["by_status"].items():  # type: ignore[union-attr]
        lines.append(f"- {status}: {count}")
    lines.extend([
        "",
        "## Operation Registry",
        "",
        "| Operation | Provider | Status | Exposure | Mutability | Confirmation |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for operation in STORE_OPERATIONS:
        lines.append(
            f"| `{operation.operation_id}` | {operation.provider} | {operation.status} | "
            f"{operation.exposure} | {operation.mutability} | {operation.confirmation_required} |"
        )
    lines.extend([
        "",
        "## API Categories",
        "",
        "| Provider | Category | Status | Source | Notes |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row in rows:
        lines.append(
            f"| {row['provider']} | `{row['category']}` | {row['status']} | {row['source']} | {row['notes']} |"
        )
    lines.append("")
    return "\n".join(lines)


def coverage_payload(provider: str | None = None, *, include_rows: bool = True) -> dict[str, object]:
    payload = {"ok": True, "summary": coverage_summary(provider)}
    if include_rows:
        payload["rows"] = list_api_coverage(provider)
    return payload
