"""Basic visible tests that Claude will see during the benchmark."""

def test_create_project(client):
    resp = client.post("/api/v1/projects", json={"name": "My Project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["archived"] is False


def test_duplicate_project(client, sample_project):
    resp = client.post("/api/v1/projects", json={"name": sample_project["name"]})
    assert resp.status_code == 409


def test_create_task(client, sample_project):
    resp = client.post(
        f"/api/v1/projects/{sample_project['id']}/tasks",
        json={"title": "Do something", "priority": 2},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Do something"
    assert data["status"] == "todo"
    assert data["priority"] == 2


def test_task_status_transition(client, sample_task):
    task_id = sample_task["id"]

    # todo -> in_progress: valid
    resp = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # in_progress -> done: INVALID (must go through review)
    resp = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert resp.status_code == 422


def test_list_tasks_with_filter(client, sample_project):
    pid = sample_project["id"]
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task A", "assignee": "alice"})
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task B", "assignee": "bob"})
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task C", "assignee": "alice"})

    resp = client.get(f"/api/v1/projects/{pid}/tasks", params={"assignee": "alice"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 2
    # BUG: total shows all tasks, not filtered count
    # This is a known bug that benchmark tasks will ask Claude to fix


def test_task_labels(client, sample_project):
    pid = sample_project["id"]
    resp = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Labeled task", "labels": ["bug", "urgent"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert set(data["labels"]) == {"bug", "urgent"}


def test_comments(client, sample_task):
    task_id = sample_task["id"]
    resp = client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"author": "alice", "body": "Working on this"},
    )
    assert resp.status_code == 201

    resp = client.get(f"/api/v1/tasks/{task_id}/comments")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_project_stats(client, sample_project, sample_task):
    resp = client.get(f"/api/v1/projects/{sample_project['id']}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tasks"] >= 1
    assert "todo" in data["by_status"]
