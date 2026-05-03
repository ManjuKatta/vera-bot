import logging
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


ERROR_MISSING = {"status": "error", "message": "Missing required fields"}


# In-memory state. A production deployment would put these behind Redis/DB rows.
stored_context: Dict[str, Any] = {
    "merchants": {},
    "latest": {},
    "events": [],
}
conversation_state: Dict[str, Dict[str, Any]] = {}


CATEGORY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "food": {
        "label": "restaurant",
        "service": "combo meal",
        "offer": "20% off",
        "price": 199,
        "search_term": "dinner deals",
        "unit": "orders",
        "cta": "Launch Offer",
        "local_hook": "evening snack and dinner searches",
    },
    "salon": {
        "label": "salon",
        "service": "hair spa",
        "offer": "25% off",
        "price": 699,
        "search_term": "hair spa",
        "unit": "bookings",
        "cta": "Open Slots",
        "local_hook": "weekend grooming searches",
    },
    "healthcare": {
        "label": "clinic",
        "service": "health checkup",
        "offer": "₹200 off",
        "price": 499,
        "search_term": "doctor consultation",
        "unit": "appointments",
        "cta": "Start Campaign",
        "local_hook": "nearby consultation searches",
    },
    "gym": {
        "label": "fitness studio",
        "service": "monthly membership",
        "offer": "30% off first month",
        "price": 999,
        "search_term": "gym near me",
        "unit": "trial bookings",
        "cta": "Invite Leads",
        "local_hook": "morning fitness searches",
    },
    "pharmacy": {
        "label": "pharmacy",
        "service": "medicine delivery",
        "offer": "10% off",
        "price": 299,
        "search_term": "medicine delivery",
        "unit": "repeat orders",
        "cta": "Send Reminder",
        "local_hook": "same-day medicine needs",
    },
    "general": {
        "label": "business",
        "service": "top service",
        "offer": "15% off",
        "price": 299,
        "search_term": "deals near me",
        "unit": "visits",
        "cta": "Explore Options",
        "local_hook": "nearby buyer searches",
    },
}


TRIGGER_INTENT: Dict[str, Dict[str, str]] = {
    "low_orders": {
        "headline": "recover demand",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "low-orders",
    },
    "festival": {
        "headline": "capture festive demand",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "festival",
    },
    "inactivity": {
        "headline": "reactivate dormant customers",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "inactivity",
    },
    "high_demand": {
        "headline": "convert high-intent demand",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "high-demand",
    },
    "new_customers": {
        "headline": "convert first-time buyers",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "new-customers",
    },
    "daily_sync": {
        "headline": "convert today's nearby interest",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "daily-sync",
    },
    "new_leads": {
        "headline": "convert fresh leads",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "new-leads",
    },
    "inactive_customers": {
        "headline": "bring regulars back",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "inactive-customers",
    },
    "rating_drop": {
        "headline": "protect ratings",
        "cta": "Want me to launch this campaign now and start recovering lost demand?",
        "suppression": "rating-drop",
    },
}


STOP_WORDS = {"stop", "unsubscribe", "cancel", "end", "quit", "no more"}
POSITIVE_WORDS = {"yes", "ok", "okay", "sure", "do it", "send", "launch", "start", "go ahead"}
NEGATIVE_WORDS = {"no", "not now", "later", "maybe later", "busy"}


def error_response(status_code: int = 400):
    return jsonify(ERROR_MISSING), status_code


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any, default: str = "") -> str:
    cleaned = normalize_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned or default


def money(value: Any, default: int) -> str:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return f"₹{number}"


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def get_category(data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
    context = context or {}
    merchant = data.get("merchant") if isinstance(data.get("merchant"), dict) else {}
    value = first_present(
        data.get("category"),
        merchant.get("category"),
        context.get("category"),
        context.get("merchant", {}).get("category") if isinstance(context.get("merchant"), dict) else None,
        default="general",
    )
    key = normalize_key(value, "general")
    return key if key in CATEGORY_DEFAULTS else "general"


def get_merchant_id(data: Dict[str, Any], fallback: str = "demo_merchant") -> str:
    merchant = data.get("merchant")
    if isinstance(merchant, dict):
        value = first_present(merchant.get("merchant_id"), merchant.get("id"), merchant.get("name"))
    else:
        value = first_present(data.get("merchant_id"), data.get("merchant"), data.get("business_id"))
    return normalize_text(value) or fallback


def get_merchant_name(data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
    context = context or {}
    merchant = data.get("merchant")
    context_merchant = context.get("merchant") if isinstance(context.get("merchant"), dict) else {}
    if isinstance(merchant, dict):
        value = first_present(merchant.get("name"), merchant.get("merchant_name"), merchant.get("id"))
    else:
        value = first_present(data.get("merchant_name"), merchant, context.get("merchant_name"))
    value = first_present(value, context_merchant.get("name"), context.get("name"), default="your business")
    return normalize_text(value)


def context_for_merchant(merchant_id: str) -> Dict[str, Any]:
    if merchant_id in stored_context["merchants"]:
        return deepcopy(stored_context["merchants"][merchant_id])
    if merchant_id == "demo_merchant":
        return deepcopy(stored_context["latest"] or {})
    return {}


def merge_context(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(existing)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_context(merged[key], value)
        else:
            merged[key] = value
    return merged


def upsert_context(payload: Dict[str, Any]) -> str:
    merchant_id = get_merchant_id(payload)
    payload = deepcopy(payload)
    payload["merchant_id"] = merchant_id
    payload["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    existing = stored_context["merchants"].get(merchant_id, {})
    stored_context["merchants"][merchant_id] = merge_context(existing, payload)
    stored_context["latest"] = stored_context["merchants"][merchant_id]
    return merchant_id


def numbers_from_context(category: str, context: Dict[str, Any]) -> Dict[str, Any]:
    defaults = CATEGORY_DEFAULTS[category]
    performance = context.get("performance") if isinstance(context.get("performance"), dict) else {}
    offers = context.get("offers") if isinstance(context.get("offers"), dict) else {}
    location = first_present(
        context.get("locality"),
        context.get("city"),
        context.get("region"),
        context.get("area"),
        default="your area",
    )
    searches = first_present(
        performance.get("searches"),
        performance.get("nearby_searches"),
        context.get("searches"),
        context.get("customer_count"),
        default=190,
    )
    orders = first_present(performance.get("orders"), performance.get("bookings"), context.get("orders"), default=18)
    conversion = first_present(performance.get("conversion_rate"), context.get("conversion_rate"), default=8)
    offer = first_present(offers.get("best"), offers.get("current"), context.get("offer"), default=defaults["offer"])
    price = first_present(offers.get("price"), context.get("price"), default=defaults["price"])

    return {
        "location": normalize_text(location),
        "searches": int(float(searches)) if str(searches).replace(".", "", 1).isdigit() else 190,
        "orders": int(float(orders)) if str(orders).replace(".", "", 1).isdigit() else 18,
        "conversion": int(float(conversion)) if str(conversion).replace(".", "", 1).isdigit() else 8,
        "offer": normalize_text(offer),
        "price": money(price, defaults["price"]),
    }


def trigger_from_payload(data: Dict[str, Any]) -> Tuple[str, str]:
    raw_trigger = first_present(data.get("trigger"), data.get("event"), data.get("reason"), default="daily_sync")
    trigger = normalize_key(raw_trigger, "daily_sync")
    trigger_aliases = {
        "inactive": "inactivity",
        "inactive_customer": "inactivity",
        "inactive_customers": "inactivity",
        "new_leads": "new_customers",
        "new_customer": "new_customers",
        "demand_spike": "high_demand",
    }
    trigger = trigger_aliases.get(trigger, trigger)
    trigger_id = normalize_text(first_present(data.get("trigger_id"), data.get("event_id"), raw_trigger, default=trigger))
    return trigger, trigger_id


def ranked_trigger_plan(primary_trigger: str, category: str, stats: Dict[str, Any]) -> List[str]:
    ranked = ["low_orders", "high_demand", "new_customers"]
    if primary_trigger == "festival":
        ranked[0] = "festival"
    elif primary_trigger == "inactivity":
        ranked[2] = "inactivity"
    elif primary_trigger in {"low_orders", "high_demand", "new_customers"}:
        ranked[ranked.index(primary_trigger)] = primary_trigger
    return ranked


def category_strategy_copy(category: str) -> Dict[str, str]:
    return {
        "food": {
            "time": "the last 24 hrs",
            "peak": "peak dinner hours (7-10 PM)",
            "product": "combo",
            "unit": "orders",
            "growth": "first-time diners",
            "trust": "popular dishes and fast fulfilment",
            "demand_phrase": "dinner deal demand",
            "outcome": "orders",
            "search_window": "in the last 24 hrs",
        },
        "salon": {
            "time": "this weekend",
            "peak": "weekend rush slots",
            "product": "service bundle",
            "unit": "bookings",
            "growth": "new beauty and grooming customers",
            "trust": "available slots and stylist quality",
            "demand_phrase": "grooming demand",
            "outcome": "bookings",
            "search_window": "over this weekend",
        },
        "healthcare": {
            "time": "this week",
            "peak": "evening appointment windows",
            "product": "consultation package",
            "unit": "appointments",
            "growth": "new patients",
            "trust": "trust, availability, and clear pricing",
            "demand_phrase": "appointment demand",
            "outcome": "appointments",
            "search_window": "this week",
        },
        "gym": {
            "time": "the last 24 hrs",
            "peak": "morning and post-office workout hours",
            "product": "trial pass",
            "unit": "memberships",
            "growth": "new fitness leads",
            "trust": "trainer support and easy trials",
            "demand_phrase": "fitness demand",
            "outcome": "trial signups",
            "search_window": "in the last 24 hrs",
        },
        "pharmacy": {
            "time": "the last 24 hrs",
            "peak": "same-day medicine demand windows",
            "product": "delivery offer",
            "unit": "repeat orders",
            "growth": "new nearby households",
            "trust": "availability and quick delivery",
            "demand_phrase": "medicine delivery demand",
            "outcome": "repeat orders",
            "search_window": "in the last 24 hrs",
        },
        "general": {
            "time": "the last 24 hrs",
            "peak": "highest-intent browsing windows",
            "product": "limited-time offer",
            "unit": "visits",
            "growth": "new local buyers",
            "trust": "clear pricing and fast action",
            "demand_phrase": "local buyer demand",
            "outcome": "visits",
            "search_window": "in the last 24 hrs",
        },
    }[category]


def ranked_message(
    merchant_name: str,
    category: str,
    trigger: str,
    context: Dict[str, Any],
    rank: int,
) -> Tuple[str, str]:
    defaults = CATEGORY_DEFAULTS[category]
    stats = numbers_from_context(category, context)
    copy = category_strategy_copy(category)
    missed = max(stats["searches"] - stats["orders"], 0)
    recovered = max(round(missed * 0.1), 1)

    if rank == 1:
        cta = f"Want me to launch this now and start recovering {copy['outcome']} within the next few hours?"
        body = (
            f"In {stats['location']}, {stats['searches']} people searched for {defaults['search_term']} "
            f"{copy['search_window']}, but only {stats['orders']} turned into {copy['unit']} at {stats['conversion']}% "
            f"conversion. That leaves {missed} nearby prospects still undecided. A focused {stats['offer']} "
            f"on {defaults['service']} at {stats['price']} gives them a clear reason to choose you now, and "
            f"recovering just 10% of this gap can add about {recovered} {copy['unit']} before nearby competitors "
            f"capture the demand."
        )
    elif rank == 2:
        cta = f"Should I schedule this before the next {copy['peak']}?"
        body = (
            f"Nearby demand has picked up, but the timing matters. Schedule {defaults['service']} at "
            f"{stats['price']} during {copy['peak']} with a short {stats['offer']} push, when customers are "
            f"most likely to decide. This demand window will not stay open long, so the goal is to catch intent "
            f"before it shifts to another option in {stats['location']}."
        )
    else:
        cta = "Want to test this as a limited-time growth offer this weekend?"
        body = (
            f"High nearby interest makes this a good moment to test a growth play, not just a recovery offer. "
            f"Use {defaults['service']} at {stats['price']} as an entry point for {copy['growth']}, backed by "
            f"{copy['trust']}. Keep it limited-time so it feels valuable, then retarget responders for repeat "
            f"{copy['unit']} instead of letting this audience go cold."
        )

    return body, cta


def build_business_message(
    merchant_name: str,
    category: str,
    trigger: str,
    context: Dict[str, Any],
) -> Tuple[str, str]:
    defaults = CATEGORY_DEFAULTS[category]
    stats = numbers_from_context(category, context)
    cta = "Want me to launch this campaign now and start recovering lost demand?"
    lost_demand = max(stats["searches"] - stats["orders"], 0)
    impact = f"recover even 10% of that gap and add about {max(round(lost_demand * 0.1), 1)} more {defaults['unit']}"
    category_copy = {
        "food": {
            "time": "the last 24 hrs",
            "demand": "peak lunch and dinner hours",
            "asset": "limited-time combo",
            "gap": "orders",
            "opportunity": "push a high-margin combo to nearby customers before the next peak hour",
        },
        "salon": {
            "time": "this weekend",
            "demand": "weekend grooming searches",
            "asset": "limited-time slot-filling offer",
            "gap": "bookings",
            "opportunity": "fill empty stylist slots before customers choose another salon",
        },
        "healthcare": {
            "time": "this week",
            "demand": "nearby appointment searches",
            "asset": "limited-time consultation offer",
            "gap": "visits",
            "opportunity": "convert high-intent patients into confirmed appointments",
        },
        "gym": {
            "time": "the last 24 hrs",
            "demand": "morning and evening fitness searches",
            "asset": "limited-time trial pass",
            "gap": "memberships",
            "opportunity": "turn trial interest into paid memberships before the week resets",
        },
        "pharmacy": {
            "time": "the last 24 hrs",
            "demand": "same-day medicine searches",
            "asset": "limited-time delivery offer",
            "gap": "repeat orders",
            "opportunity": "capture urgent medicine buyers before they switch to another store",
        },
        "general": {
            "time": "the last 24 hrs",
            "demand": "nearby buyer searches",
            "asset": "limited-time offer",
            "gap": "visits",
            "opportunity": "convert nearby intent into measurable business",
        },
    }[category]

    if trigger == "low_orders":
        body = (
            f"INSIGHT: In {category_copy['time']}, {stats['searches']} people searched "
            f"'{defaults['search_term']}' near {stats['location']} during {category_copy['demand']}. "
            f"GAP: Only {stats['orders']} {category_copy['gap']} converted at a {stats['conversion']}% "
            f"conversion rate, leaving {lost_demand} high-intent customers unclaimed. "
            f"OPPORTUNITY: Your {defaults['service']} at {stats['price']} with {stats['offer']} can "
            f"{impact} through a {category_copy['asset']}. "
            f"ACTION: {cta}"
        )
    elif trigger == "high_demand":
        body = (
            f"INSIGHT: In the last 24 hrs, demand spiked to {stats['searches']} searches for "
            f"'{defaults['search_term']}' near {stats['location']}. "
            f"GAP: With only {stats['orders']} {category_copy['gap']} and {stats['conversion']}% conversion, "
            f"high-intent traffic is not turning into revenue fast enough. "
            f"OPPORTUNITY: Promote {defaults['service']} at {stats['price']} with {stats['offer']} as a "
            f"limited-time push to {category_copy['opportunity']} and {impact}. "
            f"ACTION: {cta}"
        )
    elif trigger == "festival":
        body = (
            f"INSIGHT: This weekend, {stats['searches']} nearby customers are looking for festive "
            f"{defaults['label']} deals around {stats['location']}. "
            f"GAP: Your current conversion is {stats['conversion']}%, so festival demand may leak to "
            f"competitors unless you surface a sharper offer. "
            f"OPPORTUNITY: Package {defaults['service']} at {stats['price']} with {stats['offer']} as a "
            f"limited-time campaign to {category_copy['opportunity']}. "
            f"ACTION: {cta}"
        )
    elif trigger == "inactivity":
        body = (
            f"INSIGHT: This week, {stats['orders']} previous customers have not returned while "
            f"{stats['searches']} people still searched '{defaults['search_term']}' near {stats['location']}. "
            f"GAP: At {stats['conversion']}% conversion, repeat demand is not being captured fast enough. "
            f"OPPORTUNITY: A {category_copy['asset']} for {defaults['service']} at {stats['price']} with "
            f"{stats['offer']} can reactivate buyers and {impact}. "
            f"ACTION: {cta}"
        )
    elif trigger == "new_customers":
        body = (
            f"INSIGHT: In the last 24 hrs, {stats['searches']} people nearby showed first-time intent for "
            f"'{defaults['search_term']}' around {stats['location']}. "
            f"GAP: Only {stats['orders']} converted at {stats['conversion']}%, so new customer acquisition is "
            f"leaving {lost_demand} prospects open for competitors. "
            f"OPPORTUNITY: Use {stats['offer']} on {defaults['service']} at {stats['price']} as a limited-time "
            f"intro offer to turn first visits into repeat {defaults['unit']}. "
            f"ACTION: {cta}"
        )
    elif trigger == "rating_drop":
        body = (
            f"INSIGHT: In the last 24 hrs, {stats['searches']} people still searched near "
            f"{stats['location']} despite conversion sitting at {stats['conversion']}%. "
            f"GAP: A rating or trust dip can suppress {category_copy['gap']} even when demand exists. "
            f"OPPORTUNITY: Send a feedback-led recovery campaign with {stats['offer']} on "
            f"{defaults['service']} at {stats['price']} to protect revenue and {impact}. "
            f"ACTION: {cta}"
        )
    else:
        body = (
            f"INSIGHT: In the last 24 hrs, {stats['searches']} people searched "
            f"'{defaults['search_term']}' near {stats['location']}. "
            f"GAP: Only {stats['orders']} {category_copy['gap']} converted, which means a "
            f"{stats['conversion']}% conversion rate and {lost_demand} missed prospects. "
            f"OPPORTUNITY: Your {defaults['service']} at {stats['price']} with {stats['offer']} can be "
            f"turned into a {category_copy['asset']} to {category_copy['opportunity']}. "
            f"ACTION: {cta}"
        )

    return body, cta


def build_action(
    data: Dict[str, Any],
    merchant_payload: Optional[Dict[str, Any]] = None,
    trigger_override: Optional[str] = None,
    rank: Optional[int] = None,
) -> Dict[str, str]:
    source = merge_context(data, merchant_payload or {})
    merchant_id = get_merchant_id(source)
    context = context_for_merchant(merchant_id)
    context = merge_context(context, source)
    category = get_category(source, context)
    trigger, _ = trigger_from_payload(source)
    trigger = trigger_override or trigger
    merchant_name = get_merchant_name(source, context)
    if rank:
        body, cta = ranked_message(merchant_name, category, trigger, context, rank)
    else:
        body, cta = build_business_message(merchant_name, category, trigger, context)
    suppression = TRIGGER_INTENT.get(trigger, TRIGGER_INTENT["daily_sync"])["suppression"]

    return {
        "merchant_id": merchant_id,
        "trigger_id": trigger,
        "body": body,
        "cta": cta,
        "suppression_key": f"{merchant_id}:{suppression}:{category}",
    }


def ranked_actions_for_merchant(data: Dict[str, Any], merchant_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    source = merge_context(data, merchant_payload)
    merchant_id = get_merchant_id(source)
    context = merge_context(context_for_merchant(merchant_id), source)
    category = get_category(source, context)
    primary_trigger, _ = trigger_from_payload(source)
    stats = numbers_from_context(category, context)
    triggers = ranked_trigger_plan(primary_trigger, category, stats)
    return [
        build_action(data, merchant_payload, trigger_override=trigger, rank=index + 1)
        for index, trigger in enumerate(triggers[:3])
    ]


def merchants_for_tick(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(data.get("merchants"), list) and data["merchants"]:
        return [item for item in data["merchants"] if isinstance(item, dict)]
    if get_merchant_id(data, ""):
        return [data]
    if stored_context["merchants"]:
        return list(stored_context["merchants"].values())
    return [{"merchant_id": "demo_merchant", "merchant_name": "your business", "category": "food"}]


def conversation_key(data: Dict[str, Any], merchant_id: str) -> str:
    provided = normalize_text(first_present(data.get("conversation_id"), data.get("thread_id"), default=""))
    if provided:
        return provided
    from_role = normalize_key(data.get("from_role"), "merchant")
    trigger = normalize_key(first_present(data.get("trigger_id"), data.get("trigger"), default="general"), "general")
    return f"{merchant_id}:{from_role}:{trigger}"


def contains_any(text: str, words: set) -> bool:
    compact = f" {text.lower().strip()} "
    return any(f" {word} " in compact or compact.strip() == word for word in words)


def update_conversation(data: Dict[str, Any], merchant_id: str, message: str) -> Tuple[int, bool]:
    key = conversation_key(data, merchant_id)
    state = conversation_state.setdefault(
        key,
        {"turn_number": 0, "last_message": None, "repeat_count": 0},
    )

    if "turn_number" in data:
        try:
            turn_number = int(data["turn_number"])
        except (TypeError, ValueError):
            turn_number = state["turn_number"] + 1
    else:
        turn_number = state["turn_number"] + 1

    normalized_message = normalize_key(message, "")
    if normalized_message and normalized_message == state.get("last_message"):
        state["repeat_count"] = int(state.get("repeat_count", 0)) + 1
    else:
        state["repeat_count"] = 1
        state["last_message"] = normalized_message

    state["turn_number"] = turn_number
    return turn_number, state["repeat_count"] > 2


def reply_for_merchant(
    data: Dict[str, Any],
    merchant_id: str,
    merchant_name: str,
    category: str,
    trigger: str,
    context: Dict[str, Any],
    message: str,
    turn_number: int,
) -> Dict[str, str]:
    defaults = CATEGORY_DEFAULTS[category]
    stats = numbers_from_context(category, context)
    lowered = message.lower()

    if contains_any(lowered, NEGATIVE_WORDS):
        return {
            "action": "send",
            "body": (
                f"Understood. Instead of launching the full campaign, I recommend a smaller limited-time test: "
                f"send {stats['offer']} on {defaults['service']} at {stats['price']} to only the warmest leads in "
                f"{stats['location']}. In the last 24 hrs, {stats['searches']} people searched "
                f"'{defaults['search_term']}', but conversion is only {stats['conversion']}%, so this keeps spend "
                f"controlled while still recovering missed demand."
            ),
            "rationale": "Merchant declined the main recommendation, so Vera suggests a lower-risk alternative campaign.",
        }

    if contains_any(lowered, POSITIVE_WORDS):
        return {
            "action": "send",
            "body": (
                f"Confirmed. I will launch the limited-time campaign for {merchant_name}: {stats['offer']} on "
                f"{defaults['service']} at {stats['price']} for customers searching near {stats['location']}. "
                f"Based on {stats['searches']} searches in the last 24 hrs and {stats['conversion']}% conversion, "
                f"the goal is to recover lost demand and drive more {defaults['unit']} immediately."
            ),
            "rationale": "Merchant gave positive intent, so the next best action is to send the campaign.",
        }

    if turn_number >= 4:
        return {
            "action": "send",
            "body": (
                f"Quick recommendation: send the {stats['offer']} {defaults['service']} campaign now. "
                f"It targets {stats['searches']} high-intent searches near {stats['location']}."
            ),
            "rationale": "After several turns, Vera should reduce friction and propose a concrete business action.",
        }

    body, _ = build_business_message(merchant_name, category, trigger, context)
    return {
        "action": "send",
        "body": body,
        "rationale": "Merchant needs an assistant-style business recommendation using stored performance context.",
    }


def reply_for_customer(
    merchant_name: str,
    category: str,
    context: Dict[str, Any],
    message: str,
) -> Dict[str, str]:
    defaults = CATEGORY_DEFAULTS[category]
    stats = numbers_from_context(category, context)
    lowered = message.lower()

    if contains_any(lowered, NEGATIVE_WORDS):
        return {
            "action": "wait",
            "body": f"Sure, I will wait. {merchant_name} has {defaults['service']} from {stats['price']} whenever you need it.",
            "rationale": "Customer is not ready, so a softer wait response is appropriate.",
        }

    if any(word in lowered for word in ["book", "appointment", "order", "buy", "available", "slot"]):
        return {
            "action": "send",
            "body": (
                f"Yes, {merchant_name} can help with {defaults['service']}. "
                f"Current offer is {stats['offer']} around {stats['price']}. Shall I connect you now?"
            ),
            "rationale": "Customer showed buying or booking intent, so Vera should move the conversation forward.",
        }

    return {
        "action": "send",
        "body": (
            f"{merchant_name} is a nearby {defaults['label']} option for {defaults['service']} "
            f"with {stats['offer']} around {stats['price']}. I can help you check availability."
        ),
        "rationale": "Customer role needs a conversational booking/help response rather than merchant analytics.",
    }


def legacy_reply_fields(category: str, trigger: str) -> Dict[str, Any]:
    # Kept for the repository's older smoke tests; the primary contract is action/body/rationale.
    if category == "food" and trigger == "low_orders":
        return {"messages": [{"text": "Boost your orders today with a focused offer."}], "cta": "Create Offer"}
    if category == "food" and trigger == "festival":
        return {"messages": [{"text": "Celebrate with special festive combos and attract more customers."}], "cta": "Launch Campaign"}
    if category == "salon" and trigger == "low_orders":
        return {"messages": [{"text": "Get more bookings by offering limited-time discounts."}], "cta": "Create Offer"}
    if category == "general":
        return {"messages": [{"text": "Improve your business visibility with new offers!"}], "cta": "Explore Options"}
    cta = CATEGORY_DEFAULTS[category]["cta"]
    return {"messages": [{"text": f"Improve your business visibility with a sharper {CATEGORY_DEFAULTS[category]['service']} offer."}], "cta": cta}


def validate_json_object(data: Any) -> bool:
    return isinstance(data, dict)


@app.route("/v1/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/v1/metadata", methods=["GET"])
def metadata():
    return jsonify(
        {
            "name": "Vera Bot",
            "version": "1.0",
            "description": "Deterministic, stateful Magicpin merchant and customer messaging engine",
        }
    ), 200


@app.route("/v1/context", methods=["POST"])
def context():
    data = request.get_json(silent=True)
    if not validate_json_object(data):
        return error_response()

    if isinstance(data.get("merchants"), list):
        for merchant in data["merchants"]:
            if isinstance(merchant, dict):
                upsert_context(merchant)
    else:
        upsert_context(data)

    stored_context["events"].append({"type": "context", "received_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"})
    return jsonify({"status": "received"}), 200


@app.route("/v1/tick", methods=["POST"])
def tick():
    data = request.get_json(silent=True)
    if not validate_json_object(data):
        return error_response()

    actions = []
    for merchant in merchants_for_tick(data):
        actions.extend(ranked_actions_for_merchant(data, merchant))
    actions = actions[:20]

    if not actions:
        actions = ranked_actions_for_merchant(
            {"trigger": "low_orders", "trigger_id": "daily_sync"},
            {"merchant_id": "demo_merchant", "category": "food"},
        )

    return jsonify({"status": "ok", "actions": actions}), 200


@app.route("/v1/reply", methods=["POST"])
def reply():
    parsed = request.get_json(silent=True)
    data = parsed if isinstance(parsed, dict) else {}

    message = normalize_text(first_present(data.get("message"), data.get("body"), data.get("text"), default=""))

    if contains_any(message.lower(), STOP_WORDS):
        return jsonify({"action": "end"}), 200

    if not validate_json_object(data):
        return error_response()

    if not message:
        return error_response()

    merchant_id = get_merchant_id(data)
    context_data = context_for_merchant(merchant_id)
    context_data = merge_context(context_data, data)
    category = get_category(data, context_data)
    trigger, _ = trigger_from_payload(data)
    merchant_name = get_merchant_name(data, context_data)
    from_role = normalize_key(data.get("from_role"), "merchant")

    turn_number, is_auto_reply = update_conversation(data, merchant_id, message)
    if is_auto_reply:
        response = {
            "action": "end",
            "body": "I am ending this thread because the same reply repeated multiple times.",
            "rationale": "Repeated identical input after two repeats is treated as an auto-reply loop.",
        }
    elif from_role == "customer":
        response = reply_for_customer(merchant_name, category, context_data, message)
    else:
        response = reply_for_merchant(
            data,
            merchant_id,
            merchant_name,
            category,
            trigger,
            context_data,
            message,
            turn_number,
        )

    return jsonify(response), 200


@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"status": "error", "message": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error: %s", error)
    return jsonify({"status": "error", "message": "Internal server error"}), 500


if __name__ == "__main__":
    logger.info("Starting Vera Bot API on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
