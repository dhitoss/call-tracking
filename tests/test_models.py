def test_call_sid_length(self):
    """Testa validação de tamanho do call_sid."""
    with pytest.raises(ValidationError):
        CallRecord(
            call_sid="CA123",  # Muito curto (5 chars, precisa 34)
            from_number="+5561999998888",
            to_number="+551133334444",
            status="completed"
        )

def test_valid_call_sid(self):
    """Testa call_sid válido com exatamente 34 caracteres."""
    call = CallRecord(
        call_sid="CA" + "1" * 32,  # Exatamente 34 chars
        from_number="+5561999998888",
        to_number="+551133334444",
        status="completed"
    )
    assert len(call.call_sid) == 34