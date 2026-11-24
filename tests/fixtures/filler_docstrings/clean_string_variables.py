def get_error_message() -> str:
    # A string variable containing a filler phrase - must NOT trigger!
    msg = "This function is responsible for nothing"
    return msg


def return_filler_literal() -> str:
    # A return statement with a filler phrase - must NOT trigger!
    return "Helper function to be returned as literal"


class ConfigHolder:
    template = "This class is responsible for template rendering"

    def report(self) -> str:
        description = "Provides a convenient way to test variables"
        return description
