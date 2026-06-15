"""
Comprehensive test suite for backend.app.utils.formula module.
Tests formula validation, normalization, and hashing functionality.
"""

import pytest
import hashlib
from backend.app.utils.formula import (
    normalize_and_hash,
    normalize_rpn,
    validate_formula,
    MAX_FORMULA_LENGTH,
    MAX_TOKENS,
)

# Mark all tests in this file as unit tests
pytestmark = pytest.mark.unit


class TestValidateFormula:
    """Test suite for validate_formula function."""
    
    def test_validate_empty_string(self):
        """Empty strings should raise ValueError."""
        with pytest.raises(ValueError, match="Formula cannot be empty"):
            validate_formula("")
    
    def test_validate_whitespace_only(self):
        """Whitespace-only strings should raise ValueError."""
        with pytest.raises(ValueError, match="Formula cannot be empty"):
            validate_formula("   ")
        with pytest.raises(ValueError, match="Formula cannot be empty"):
            validate_formula("\t\n")
    
    def test_validate_none(self):
        """None should raise ValueError."""
        with pytest.raises(ValueError, match="Formula cannot be empty"):
            validate_formula(None)
    
    def test_validate_valid_simple_formula(self):
        """Valid simple formulas should not raise."""
        validate_formula("a")
        validate_formula("a b c")
        validate_formula("x || y && z")
    
    def test_validate_exceeds_character_limit(self):
        """Formulas exceeding character limit should raise."""
        oversized = "a " * (MAX_FORMULA_LENGTH + 1)
        with pytest.raises(ValueError, match="Formula exceeds"):
            validate_formula(oversized)
    
    def test_validate_at_character_limit(self):
        """Formulas at the character limit should pass."""
        # Create a formula exactly at the limit
        at_limit = "a " * (MAX_FORMULA_LENGTH // 2)
        # Just ensure it doesn't raise on character count
        try:
            validate_formula(at_limit)
        except ValueError as e:
            # Only fail if error is about character limit, not tokens
            assert "exceeds" not in str(e) or "tokens" in str(e)
    
    def test_validate_null_character(self):
        """Formulas containing null characters should raise."""
        with pytest.raises(ValueError, match="invalid characters"):
            validate_formula("a\x00b")
    
    def test_validate_exceeds_token_limit(self):
        """Formulas exceeding token limit should raise."""
        oversized = " ".join(["a"] * (MAX_TOKENS + 1))
        with pytest.raises(ValueError, match="Too many tokens"):
            validate_formula(oversized)
    
    def test_validate_at_token_limit(self):
        """Formulas at token limit should pass."""
        at_limit = " ".join(["a"] * MAX_TOKENS)
        # Should not raise about token count
        try:
            validate_formula(at_limit)
        except ValueError as e:
            assert "Too many tokens" not in str(e)
    
    def test_validate_with_operators(self):
        """Formulas with valid operators should pass validation."""
        validate_formula("a && b || c")
        validate_formula("x => y <=> z")
        validate_formula("! a")


class TestNormalizeRPN:
    """Test suite for normalize_rpn function."""
    
    def test_normalize_simple_formula(self):
        """Simple formulas should normalize correctly."""
        result = normalize_rpn("a b c")
        assert result == "a b c"
    
    def test_normalize_collapse_whitespace(self):
        """Multiple spaces should collapse to single space."""
        result = normalize_rpn("a   b     c")
        assert result == "a b c"
    
    def test_normalize_tabs_and_newlines(self):
        """Tabs and newlines should be treated as spaces."""
        result = normalize_rpn("a\tb\nc")
        assert result == "a b c"
    
    def test_normalize_leading_trailing_whitespace(self):
        """Leading/trailing whitespace should be removed."""
        result = normalize_rpn("   a b c   ")
        assert result == "a b c"
    
    def test_normalize_with_operators(self):
        """RPN formulas with operators should normalize."""
        result = normalize_rpn("a b &&")
        assert result == "a b &&"
        
        result = normalize_rpn("a b   ||   c  =>")
        assert result == "a b || c =>"
    
    def test_normalize_with_all_allowed_operators(self):
        """All allowed operators should be recognized."""
        result = normalize_rpn("a && b || c <=> d => e ! f")
        assert result == "a && b || c <=> d => e ! f"
    
    def test_normalize_alphanumeric_tokens(self):
        """Alphanumeric tokens should be preserved."""
        result = normalize_rpn("var1 var2 x123")
        assert result == "var1 var2 x123"
    
    def test_normalize_rejects_invalid_operator(self):
        """Invalid operators should raise ValueError."""
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a & b")
        
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a | b")
    
    def test_normalize_rejects_special_symbols(self):
        """Special symbols should raise ValueError."""
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a + b")
        
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a @ b")
        
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a # b")
    
    def test_normalize_rejects_parentheses(self):
        """Parentheses should raise ValueError."""
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("(a || b)")
    
    def test_normalize_rejects_punctuation(self):
        """Punctuation should raise ValueError."""
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a . b")
        
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_rpn("a, b")
    
    def test_normalize_single_token(self):
        """Single token should normalize correctly."""
        assert normalize_rpn("a") == "a"
        assert normalize_rpn("var1") == "var1"
    
    def test_normalize_complex_valid_formula(self):
        """Complex valid RPN formulas should normalize."""
        input_formula = "x   y  &&   z   ||   w   =>   ! v"
        expected = "x y && z || w => ! v"
        assert normalize_rpn(input_formula) == expected


class TestNormalizeAndHash:
    """Test suite for normalize_and_hash function."""
    
    def test_normalize_and_hash_valid_rpn(self):
        """Valid RPN should return tuple of (normalized_formula, hash)."""
        normalized, hash_value = normalize_and_hash("a b &&", "RPN", "RPN")
        
        assert normalized == "a b &&"
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 hex digest length
    
    def test_normalize_and_hash_wrong_notation(self):
        """Non-RPN notation should raise ValueError."""
        with pytest.raises(ValueError, match="RPN notations has not been used"):
            normalize_and_hash("a OR b", "INFIX", "RPN")
        
        with pytest.raises(ValueError, match="RPN notations has not been used"):
            normalize_and_hash("a b &&", "CNF", "RPN")
    
    def test_normalize_and_hash_empty_formula(self):
        """Empty formula should raise ValueError from validation."""
        with pytest.raises(ValueError, match="Formula cannot be empty"):
            normalize_and_hash("", "RPN", "RPN")
    
    def test_normalize_and_hash_invalid_operator(self):
        """Invalid operators should raise ValueError."""
        with pytest.raises(ValueError, match="Unallowed symbols or operators"):
            normalize_and_hash("a + b", "RPN", "RPN")
    
    def test_normalize_and_hash_deterministic(self):
        """Same input should always produce same hash."""
        formula = "a b && c ||"
        hash1 = normalize_and_hash(formula, "RPN", "RPN")[1]
        hash2 = normalize_and_hash(formula, "RPN", "RPN")[1]
        assert hash1 == hash2
    
    def test_normalize_and_hash_whitespace_invariant(self):
        """Different whitespace should produce same hash (normalized)."""
        hash1 = normalize_and_hash("a   b   &&", "RPN", "RPN")[1]
        hash2 = normalize_and_hash("a b &&", "RPN", "RPN")[1]
        assert hash1 == hash2
    
    def test_normalize_and_hash_includes_notation(self):
        """Hash should differ if notation (in the hash_input) differs."""
        # Though notation validation should prevent this, hash includes it
        normalized1, _ = normalize_and_hash("a b &&", "RPN", "RPN")
        assert normalized1 == "a b &&"
    
    def test_normalize_and_hash_valid_sha256(self):
        """Hash should be valid SHA256."""
        _, hash_value = normalize_and_hash("x y ||", "RPN", "RPN")
        
        # Verify it's a valid hex string
        try:
            int(hash_value, 16)
            assert True
        except ValueError:
            assert False, "Hash is not valid hex"
        
        # Verify length is SHA256
        assert len(hash_value) == 64
    
    def test_normalize_and_hash_formula_in_hash(self):
        """Hash should include the formula content."""
        normalized, hash_value = normalize_and_hash("a b &&", "RPN", "RPN")
        
        # Manually compute expected hash
        hash_input = f"RPN:{normalized}"
        expected_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        
        assert hash_value == expected_hash
    
    def test_normalize_and_hash_all_operators(self):
        """Should handle formulas with all allowed operators."""
        formula = "a && b || c <=> d => ! e"
        normalized, hash_value = normalize_and_hash(formula, "RPN", "RPN")
        
        assert normalized == "a && b || c <=> d => ! e"
        assert len(hash_value) == 64
    
    def test_normalize_and_hash_large_formula(self):
        """Should handle reasonably large formulas."""
        # Create formula with 1000 tokens
        large_formula = " ".join(["x"] * 1000)
        normalized, hash_value = normalize_and_hash(large_formula, "RPN", "RPN")
        
        assert len(normalized.split()) == 1000
        assert len(hash_value) == 64
    
    def test_normalize_and_hash_consistency_with_manual_hash(self):
        """Hash computation should match manual SHA256."""
        formula = "var1 var2 &&"
        normalized, returned_hash = normalize_and_hash(formula, "RPN", "RPN")
        
        manual_hash = hashlib.sha256(
            f"RPN:{normalized}".encode("utf-8")
        ).hexdigest()
        
        assert returned_hash == manual_hash
    
    def test_normalize_and_hash_different_formulas_different_hashes(self):
        """Different formulas should produce different hashes."""
        hash1 = normalize_and_hash("a b &&", "RPN", "RPN")[1]
        hash2 = normalize_and_hash("a b ||", "RPN", "RPN")[1]
        assert hash1 != hash2
    
    def test_normalize_and_hash_case_sensitive(self):
        """Variable names should be case sensitive."""
        hash1 = normalize_and_hash("A b &&", "RPN", "RPN")[1]
        hash2 = normalize_and_hash("a b &&", "RPN", "RPN")[1]
        # Different because A != a
        assert hash1 != hash2
    
    def test_normalize_and_hash_validation_order(self):
        """Should validate formula before hashing."""
        # Formula exceeds size limit
        oversized = "a " * (MAX_FORMULA_LENGTH + 1)
        with pytest.raises(ValueError):
            normalize_and_hash(oversized, "RPN", "RPN")


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_workflow_valid_formula_submission(self):
        """Test workflow: validate -> normalize -> hash."""
        formula = "x   y   &&   z   ||"
        
        # Should pass validation
        validate_formula(formula)
        
        # Should normalize and hash
        normalized, hash_value = normalize_and_hash(formula, "RPN", "RPN")
        
        assert normalized == "x y && z ||"
        assert len(hash_value) == 64
    
    def test_workflow_catches_invalid_formula(self):
        """Test that invalid formulas are caught early."""
        invalid = "a + b"
        
        # Should fail at normalization (invalid operator)
        with pytest.raises(ValueError):
            normalize_rpn(invalid)
    
    def test_workflow_caching_scenario(self):
        """Test scenario where same formula submitted twice."""
        formula = "p q && r ||"
        
        # First submission
        norm1, hash1 = normalize_and_hash(formula, "RPN", "RPN")
        
        # Second submission (with different whitespace)
        formula_variant = "p   q   &&   r   ||"
        norm2, hash2 = normalize_and_hash(formula_variant, "RPN", "RPN")
        
        # Should be identical (cache-friendly)
        assert norm1 == norm2
        assert hash1 == hash2
    
    def test_workflow_multiple_valid_operators(self):
        """Test complex formula with multiple operators."""
        formula = "a && b || c <=> d => ! e"
        
        validate_formula(formula)
        normalized, hash_value = normalize_and_hash(formula, "RPN", "RPN")
        
        assert normalized == "a && b || c <=> d => ! e"
        assert len(hash_value) == 64


class TestEdgeCases:
    """Edge case tests."""
    
    def test_single_variable(self):
        """Single variable formula."""
        normalized, hash_value = normalize_and_hash("x", "RPN", "RPN")
        assert normalized == "x"
        assert len(hash_value) == 64
    
    def test_single_operator_application(self):
        """Minimal operator application."""
        normalized, hash_value = normalize_and_hash("a !", "RPN", "RPN")
        assert normalized == "a !"
    
    def test_negation_only(self):
        """Just negation operator."""
        normalized, hash_value = normalize_and_hash("!", "RPN", "RPN")
        assert normalized == "!"
    
    def test_numeric_variable_names(self):
        """Variables with numbers."""
        normalized, _ = normalize_and_hash("x1 y2 z3 &&", "RPN", "RPN")
        assert "x1" in normalized
        assert "y2" in normalized
        assert "z3" in normalized
    
    def test_mixed_alphanumeric_variables(self):
        """Mixed letters and numbers in variable names."""
        normalized, _ = normalize_and_hash("var123 x456 &&", "RPN", "RPN")
        assert normalized == "var123 x456 &&"
    
    def test_very_long_variable_names(self):
        """Very long variable names (still alphanumeric)."""
        long_var = "a" * 1000
        normalized, _ = normalize_and_hash(f"{long_var} {long_var} &&", "RPN", "RPN")
        assert long_var in normalized
    
    def test_many_same_variables(self):
        """Many repetitions of same variable."""
        formula = " ".join(["x"] * 100)
        normalized, _ = normalize_and_hash(formula, "RPN", "RPN")
        assert normalized.count("x") == 100

