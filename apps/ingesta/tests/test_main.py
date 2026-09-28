from main import main


def test_main_anuncia_servicio_listo(capsys):
    main()

    assert "Servicio de ingesta PIAs listo" in capsys.readouterr().out
