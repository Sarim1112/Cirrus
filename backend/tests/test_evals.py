from evals.run import run_accuracy, run_corruption


def test_advisor_answers_match_independent_arithmetic():
    assert run_accuracy() == []


def test_a_lying_model_can_never_change_a_figure():
    assert run_corruption() == []
