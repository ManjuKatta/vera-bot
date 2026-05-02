"""
Vera Bot API - Production-ready Flask API for deterministic merchant messaging
A merchant AI assistant that generates contextual business messages based on
category, merchant data, and trigger events.
"""

import logging
import json
from datetime import datetime
from flask import Flask, request, jsonify
from typing import Dict, Any, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Store context for reference (in-memory, production would use a database)
stored_context = {}

# ============================================================================
# DETERMINISTIC REPLY LOGIC
# ============================================================================

class VeraBotLogic:
    """Encapsulates deterministic rule-based logic for Vera Bot responses."""
    
    # Rule definitions - fully deterministic based on category and trigger
    RULES = {
        "food": {
            "low_orders": {
                "message": "Boost your orders today! Offer discounts on popular items 🍕",
                "cta": "Create Offer"
            },
            "festival": {
                "message": "Celebrate with special festive combos and attract more customers 🎉",
                "cta": "Launch Campaign"
            }
        },
        "salon": {
            "low_orders": {
                "message": "Get more bookings by offering limited-time discounts 💇",
                "cta": "Create Offer"
            }
        }
    }
    
    DEFAULT_RESPONSE = {
        "message": "Improve your business visibility with new offers!",
        "cta": "Explore Options"
    }
    
    @staticmethod
    def generate_reply(category: str, merchant: str, trigger: str) -> Dict[str, Any]:
        """
        Generate deterministic reply based on category and trigger.
        
        Args:
            category: Business category (food, salon, etc.)
            merchant: Merchant identifier/name
            trigger: Event trigger (low_orders, festival, etc.)
        
        Returns:
            Dict with 'messages' list and 'cta' string
        """
        # Normalize inputs
        category = str(category).strip().lower() if category else ""
        trigger = str(trigger).strip().lower() if trigger else ""
        
        logger.info(f"Generating reply - Category: {category}, Trigger: {trigger}, Merchant: {merchant}")
        
        # Look up rule in hierarchy
        response = None
        
        if category in VeraBotLogic.RULES:
            category_rules = VeraBotLogic.RULES[category]
            if trigger in category_rules:
                response = category_rules[trigger]
                logger.info(f"Rule matched: {category}/{trigger}")
            else:
                logger.info(f"No trigger match for {category}/{trigger}, using default")
        else:
            logger.info(f"No category match for {category}, using default")
        
        # Use default if no rule matched
        if response is None:
            response = VeraBotLogic.DEFAULT_RESPONSE
        
        # Format response
        return {
            "messages": [{"text": response["message"]}],
            "cta": response["cta"]
        }


# ============================================================================
# INPUT VALIDATION
# ============================================================================

def validate_reply_input(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate POST /v1/reply input.
    
    Args:
        data: Request JSON data
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object"
    
    # Check required fields
    required_fields = ["category", "merchant", "trigger"]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Validate field types
    for field in required_fields:
        if not isinstance(data[field], str):
            return False, f"Field '{field}' must be a string"
    
    # Validate non-empty strings
    for field in required_fields:
        if not data[field].strip():
            return False, f"Field '{field}' cannot be empty"
    
    return True, None


def validate_context_input(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate POST /v1/context input.
    
    Args:
        data: Request JSON data
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object"
    
    return True, None


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@app.route('/v1/healthz', methods=['GET'])
def healthz():
    """
    Health check endpoint.
    
    Returns:
        {"status": "ok"}
    """
    logger.info("Health check requested")
    return jsonify({"status": "ok"}), 200


@app.route('/v1/metadata', methods=['GET'])
def metadata():
    """
    Bot metadata endpoint.
    
    Returns:
        Bot information including name, version, and description
    """
    logger.info("Metadata requested")
    return jsonify({
        "name": "Vera Bot",
        "version": "1.0",
        "description": "Deterministic business messaging assistant"
    }), 200


@app.route('/v1/context', methods=['POST'])
def context():
    """
    Store or log context information.
    
    Accepts: JSON context object
    Returns: {"status": "received"}
    """
    try:
        data = request.get_json()
        
        if data is None:
            return jsonify({
                "status": "error",
                "message": "Invalid JSON"
            }), 400
        
        # Validate input
        is_valid, error_msg = validate_context_input(data)
        if not is_valid:
            logger.warning(f"Invalid context input: {error_msg}")
            return jsonify({
                "status": "error",
                "message": error_msg
            }), 400
        
        # Store context (in-memory store)
        context_id = datetime.now().isoformat()
        stored_context[context_id] = data
        
        logger.info(f"Context received and stored - ID: {context_id}")
        
        return jsonify({"status": "received"}), 200
    
    except Exception as e:
        logger.error(f"Error processing context: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500


@app.route('/v1/tick', methods=['POST'])
def tick():
    """
    Placeholder endpoint for processing events/ticks.
    
    Returns: {"status": "ok"}
    """
    try:
        data = request.get_json()
        logger.info(f"Tick received: {data}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Error processing tick: {str(e)}")
        return jsonify({"status": "ok"}), 200


@app.route('/v1/reply', methods=['POST'])
def reply():
    """
    Core logic endpoint - Generate deterministic merchant message.
    
    Accepts JSON:
    {
        "category": "string",
        "merchant": "string",
        "trigger": "string"
    }
    
    Returns:
    {
        "messages": [{"text": "message"}],
        "cta": "call_to_action"
    }
    """
    try:
        data = request.get_json()
        
        if data is None:
            logger.warning("No JSON data provided")
            return jsonify({
                "status": "error",
                "message": "Invalid JSON"
            }), 400
        
        # Validate input
        is_valid, error_msg = validate_reply_input(data)
        if not is_valid:
            logger.warning(f"Invalid reply input: {error_msg}")
            return jsonify({
                "status": "error",
                "message": error_msg
            }), 400
        
        # Extract validated fields
        category = data["category"].strip().lower()
        merchant = data["merchant"].strip()
        trigger = data["trigger"].strip().lower()
        
        # Generate deterministic reply
        reply_data = VeraBotLogic.generate_reply(category, merchant, trigger)
        
        logger.info(f"Reply generated for {merchant} | Category: {category} | Trigger: {trigger}")
        
        return jsonify(reply_data), 200
    
    except Exception as e:
        logger.error(f"Error generating reply: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    logger.warning(f"Not found: {request.path}")
    return jsonify({
        "status": "error",
        "message": "Endpoint not found"
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 Method Not Allowed errors."""
    logger.warning(f"Method not allowed: {request.method} {request.path}")
    return jsonify({
        "status": "error",
        "message": "Method not allowed"
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500


# ============================================================================
# APP INITIALIZATION
# ============================================================================

if __name__ == '__main__':
    logger.info("Starting Vera Bot API...")
    logger.info("Running on http://localhost:5000")
    logger.info("Available endpoints:")
    logger.info("  GET  /v1/healthz - Health check")
    logger.info("  GET  /v1/metadata - Bot metadata")
    logger.info("  POST /v1/context - Store context")
    logger.info("  POST /v1/tick - Process tick")
    logger.info("  POST /v1/reply - Generate message reply")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
