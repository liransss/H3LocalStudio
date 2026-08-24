from app.models.schemas import GenerationCreate, ProjectCreate


def test_repository_persists_projects_and_generations(repository):
    project = repository.create_project(ProjectCreate(name="NEXUS"))
    request = GenerationCreate(prompt="Light trails around a glass monolith", project_id=project["id"])
    generation = repository.create_generation(request, 42, "t2v", True)

    reopened = repository.get_generation(generation["id"])
    assert reopened["prompt"] == request.prompt
    assert reopened["seed"] == 42
    assert reopened["parameters"]["generation_resolution"] == "1344x768"
    assert reopened["is_mock"] is True

