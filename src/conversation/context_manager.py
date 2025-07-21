# src/conversation/context_manager.py - New conversational context management

import re
import json
from datetime import datetime
from semantic_kernel.contents.chat_history import ChatHistory
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """Store context about the last query and results"""
    query_text: str
    query_type: str  # 'sales', 'inventory', 'competitor', 'general'
    entities: Dict[str, Any]  # customers, parts, dates, etc.
    result_summary: str
    timestamp: datetime
    table_used: Optional[str] = None
    filters_applied: List[str] = None


class ConversationMemory:
    """Manages conversation state and context"""

    def __init__(self):
        self.current_context: Optional[QueryContext] = None
        self.conversation_history: List[QueryContext] = []
        # ADD THIS LINE - Create the chat_history that the kernel expects
        self.chat_history = ChatHistory()

        self.entities = {
            'customers': set(),
            'parts': set(),
            'tables': set(),
            'date_ranges': [],
            'last_customer': None,
            'last_part': None,
            'last_date_range': None
        }

    def extract_entities(self, query: str, results: str = "") -> Dict[str, Any]:
        """Extract key entities from query and results"""
        entities = {}

        # Extract customer names (patterns like CustomerA, customer names)
        customer_patterns = [
            r'Customer[A-Z]\w*',
            r'customer\s+(\w+)',
            r'buyer\s+(\w+)'
        ]

        for pattern in customer_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                entities['customers'] = matches
                self.entities['customers'].update(matches)
                self.entities['last_customer'] = matches[0]

        # Extract part numbers (OEAN patterns)
        part_patterns = [
            r'\b[A-Z]{2,4}\d{3,5}[A-Z]?\b',  # PFF5225R pattern
            r'part\s+(\w+)',
            r'filter\s+(\w+)'
        ]

        for pattern in part_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                entities['parts'] = matches
                self.entities['parts'].update(matches)
                self.entities['last_part'] = matches[0]

        # Extract date references
        date_patterns = [
            r'last\s+(month|week|year|quarter)',
            r'this\s+(month|week|year|quarter)',
            r'(\d{4})-(\d{1,2})',  # YYYY-MM
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})'
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                entities['dates'] = matches
                self.entities['last_date_range'] = str(matches[0])

        # Extract table references
        table_patterns = [
            r'ebayWT(?:_NF)?',
            r'ebayNF_SupplierMatch'
        ]

        for pattern in table_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                entities['tables'] = matches
                self.entities['tables'].update(matches)

        return entities

    def classify_query_type(self, query: str) -> str:
        """Classify the type of query for appropriate follow-ups"""
        query_lower = query.lower()

        if any(word in query_lower for word in ['revenue', 'sales', 'sold', 'purchase', 'buy']):
            return 'sales_analysis'
        elif any(word in query_lower for word in ['inventory', 'stock', 'carry', 'supplier']):
            return 'inventory_opportunity'
        elif any(word in query_lower for word in ['competitor', 'market', 'price', 'margin']):
            return 'competitor_analysis'
        elif any(word in query_lower for word in ['count', 'how many', 'records']):
            return 'data_exploration'
        else:
            return 'general'

    def update_context(self, query: str, results: str) -> None:
        """Update conversation context with new query and results"""
        entities = self.extract_entities(query, results)
        query_type = self.classify_query_type(query)

        # Extract table from query if possible
        table_used = None
        if 'ebaywt' in query.lower():
            table_used = 'ebayWT'
        elif 'ebaynf' in query.lower():
            table_used = 'ebayNF_SupplierMatch'

        # Create summary of results
        result_summary = self.create_result_summary(results)

        context = QueryContext(
            query_text=query,
            query_type=query_type,
            entities=entities,
            result_summary=result_summary,
            timestamp=datetime.now(),
            table_used=table_used,
            filters_applied=self.extract_filters(query)
        )

        self.current_context = context
        self.conversation_history.append(context)

        # Keep only last 10 conversations to prevent memory bloat
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

    def extract_filters(self, query: str) -> List[str]:
        """Extract WHERE clause filters for context"""
        filters = []

        # Look for WHERE conditions
        if 'where' in query.lower():
            where_part = query.lower().split('where')[1]
            filters.append(where_part.strip())

        return filters

    def create_result_summary(self, results: str) -> str:
        """Create a brief summary of the results"""
        if not results or len(results) < 50:
            return results

        # Extract key numbers and entities
        numbers = re.findall(r'\d{1,3}(?:,\d{3})*', results)

        if numbers:
            return f"Query returned data with key values: {', '.join(numbers[:3])}"
        else:
            return results[:100] + "..." if len(results) > 100 else results

    def add_exchange(self, question: str, response: str):
        """Add a question-response exchange to both conversation memory and chat history"""
        # Add to the kernel's chat history format
        self.chat_history.add_user_message(question)
        self.chat_history.add_assistant_message(response)

    def resolve_pronouns(self, query: str) -> str:
        """Replace pronouns and references with actual entities"""
        resolved_query = query

        # Replace "them" with last customer
        if 'them' in query.lower() and self.entities['last_customer']:
            resolved_query = resolved_query.replace(
                'them',
                self.entities['last_customer']
            )

        # Replace "that customer" with last customer
        if 'that customer' in query.lower() and self.entities['last_customer']:
            resolved_query = resolved_query.replace(
                'that customer',
                self.entities['last_customer']
            )

        # Replace "same period" with last date range
        if 'same period' in query.lower() and self.entities['last_date_range']:
            resolved_query += f" (referring to {self.entities['last_date_range']})"

        # Replace "that part" with last part
        if 'that part' in query.lower() and self.entities['last_part']:
            resolved_query = resolved_query.replace(
                'that part',
                self.entities['last_part']
            )

        return resolved_query

    def get_follow_up_suggestions(self) -> List[str]:
        """Generate contextual follow-up suggestions"""
        if not self.current_context:
            return []

        query_type = self.current_context.query_type
        entities = self.current_context.entities

        suggestions = []

        if query_type == 'sales_analysis':
            if entities.get('customers'):
                customer = entities['customers'][0]
                suggestions.extend([
                    f"Compare {customer} to other top customers",
                    f"See what other parts {customer} is buying",
                    f"Show {customer}'s purchase trends over time",
                    f"Check profit margins on {customer}'s orders"
                ])
            elif entities.get('parts'):
                part = entities['parts'][0]
                suggestions.extend([
                    f"See which customers buy {part} most",
                    f"Compare {part} to similar filter sales",
                    f"Check {part} price trends",
                    f"Find competitive pricing for {part}"
                ])

        elif query_type == 'inventory_opportunity':
            suggestions.extend([
                "Find suppliers for high-demand parts you don't carry",
                "Analyze profit potential of stocking these items",
                "Check if demand is growing or declining",
                "See competitor pricing for these parts"
            ])

        elif query_type == 'competitor_analysis':
            suggestions.extend([
                "Calculate your market share for these parts",
                "Identify parts where you could undercut prices",
                "Find their best-sellers you don't carry",
                "Track their pricing trends"
            ])

        elif query_type == 'data_exploration':
            if self.current_context.table_used:
                table = self.current_context.table_used
                suggestions.extend([
                    f"Show sample records from {table}",
                    f"Get column information for {table}",
                    f"Find most active customers in {table}",
                    f"See recent activity in {table}"
                ])

        # Add general suggestions
        suggestions.extend([
            "Export the current results to CSV",
            "Show me similar analysis for a different time period",
            "Break this down by month to show trends"
        ])

        return suggestions[:4]  # Limit to 4 suggestions

    def is_follow_up_query(self, query: str) -> bool:
        """Determine if this is a follow-up to the previous query"""
        follow_up_indicators = [
            'option', 'yes', 'no', 'show me', 'what about', 'also',
            'and', 'them', 'that', 'same', 'compare', 'break down'
        ]

        query_lower = query.lower().strip()

        # Check for option selection (1, 2, 3, etc.)
        if re.match(r'^(option\s+)?\d+$', query_lower):
            return True

        # Check for short responses
        if len(query_lower.split()) <= 3:
            return any(indicator in query_lower for indicator in follow_up_indicators)

        # Check for pronoun usage
        if any(pronoun in query_lower for pronoun in ['them', 'that', 'it', 'they']):
            return True

        return False

    def handle_follow_up_selection(self, user_input: str) -> Optional[str]:
        """Convert follow-up selection to full query"""
        if not self.current_context:
            return None

        suggestions = self.get_follow_up_suggestions()

        # Handle option number selection
        option_match = re.match(r'(?:option\s+)?(\d+)', user_input.lower().strip())
        if option_match:
            option_num = int(option_match.group(1)) - 1
            if 0 <= option_num < len(suggestions):
                return suggestions[option_num]

        # Handle "yes" to first suggestion
        if user_input.lower().strip() in ['yes', 'sure', 'ok', 'okay']:
            return suggestions[0] if suggestions else None

        return None

    def enhance_query_with_context(self, query: str) -> str:
        """Enhance query with conversational context"""
        # First resolve pronouns
        enhanced_query = self.resolve_pronouns(query)

        # If it's a follow-up, convert to full query
        if self.is_follow_up_query(query):
            follow_up_query = self.handle_follow_up_selection(query)
            if follow_up_query:
                enhanced_query = follow_up_query

        # Add context about previous query if relevant
        if self.current_context and self.is_follow_up_query(query):
            context_info = f"\n\nContext: User previously asked '{self.current_context.query_text}' "
            context_info += f"and got results showing {self.current_context.result_summary}"
            enhanced_query += context_info

        return enhanced_query

    def get_conversation_state(self) -> Dict[str, Any]:
        """Get current conversation state for debugging"""
        return {
            'current_context': asdict(self.current_context) if self.current_context else None,
            'entities': {k: list(v) if isinstance(v, set) else v for k, v in self.entities.items()},
            'history_count': len(self.conversation_history)
        }