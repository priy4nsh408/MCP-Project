from servers.read_server import get_customer


def test_customer_name_lookup_returns_matching_customers() -> None:
    customers = get_customer(name="Priya")

    assert [customer["customer_id"] for customer in customers] == [13, 33]


def test_customer_name_lookup_does_not_expose_internal_service_argument() -> None:
    result = get_customer(name="Priyal")

    assert result == []