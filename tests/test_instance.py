from unittest.mock import Mock

from localphraser.instance import activate_existing, listen, server_name


def test_second_launch_raises_only_its_own_profile(app, tmp_path):
    config = tmp_path / "config.json"
    show = Mock()
    server = listen(config, show)
    try:
        assert activate_existing(config)
        app.processEvents()
        show.assert_called_once()
        assert server_name(config) != server_name(tmp_path / "other.json")
        assert not activate_existing(tmp_path / "other.json")
    finally:
        server.close()
