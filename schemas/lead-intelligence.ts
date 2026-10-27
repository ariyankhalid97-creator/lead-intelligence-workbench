export type SourceType =
  | "live_official_website" | "website_dom" | "verified_maps_profile"
  | "recent_social_page" | "public_filing" | "third_party_directory"
  | "serp_snippet" | "dns_mx" | "smtp_verification" | "inferred_permutation";

export interface CanonicalCompany {
  parentBrandId: string;
  canonicalName: string;
  corporateDomain?: string;
  aliases: string[];
  operatingEntityIds: string[];
  firstSeen: string;
  lastSeen: string;
}

export interface OperatingLocation {
  operatingEntityId: string;
  parentBrandId?: string;
  companyId: string;
  name: string;
  localityKey: string;
  mapsPlaceId?: string;
  localPhone?: string;
  ownershipScope: "independent" | "franchise" | "corporate_branch" | "unknown";
  sourceEvidenceIds: string[];
}

export interface EvidenceClaim {
  evidenceId: string;
  companyId: string;
  operatingEntityId?: string;
  field: string;
  value: string;
  sourceType: SourceType;
  sourceUrl?: string;
  capturedAt: string;
  verbatimExcerpt: string;
  selector?: string;
  authorityWeight: number;
  freshnessWeight: number;
  trustScore: number;
}

export interface ContactRecord {
  contactId: string;
  operatingEntityId: string;
  name?: string;
  role?: string;
  email?: string;
  phone?: string;
  observationState: "published" | "inferred_permutation" | "historical_not_rediscovered";
  verificationState: "smtp_valid" | "catch_all_risk" | "mx_only" | "unverified" | "invalid";
  eligibleForOutreach: boolean;
  sourceEvidenceIds: string[];
  firstSeen: string;
  lastSeen: string;
}

export interface OutreachSequenceState {
  sequenceStateId: string;
  sequenceId: string;
  campaignId?: string;
  companyId: string;
  operatingEntityId?: string;
  email: string;
  currentStep: number;
  state: "scheduled" | "active" | "paused_ooo" | "reply_follow_up" | "halted" | "complete" | "suppressed";
  nextActionAt?: string;
  pauseUntil?: string;
  lastOutcome?: string;
  createdAt: string;
  updatedAt: string;
}
