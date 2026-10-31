from authpilot import ehr, store


def find_case(predicate, split: str = "dev"):
    """First generated case whose label matches predicate: returns (order, chart, label)."""
    for name in ehr.list_cases(split):
        order, chart, label = ehr.load_case_files(split, name)
        if predicate(label):
            return order, chart, label
    raise LookupError("no matching case")


def clean_case(procedure: str = "lumbar_mri"):
    return find_case(lambda l: l.procedure == procedure and not l.hard_case_tags)


def supplied_gap_case(procedure: str = "lumbar_mri"):
    return find_case(lambda l: l.procedure == procedure and "missing" in l.hard_case_tags
                     and l.expected_final == "approved")


def unsupplied_gap_case(procedure: str = "lumbar_mri"):
    return find_case(lambda l: l.procedure == procedure and "missing" in l.hard_case_tags
                     and l.expected_final == "escalated")


def appeal_case():
    return find_case(lambda l: "appeal_scenario" in l.hard_case_tags)


def start(case):
    order, chart, label = case
    store.create_case(label.case_id, order)
    return label.case_id
