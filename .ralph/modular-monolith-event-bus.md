## Pragmatic Modular Monolith — Workflow Direction

### Delivered
- [x] ADR-001 rewritten around explicit workflow visibility, not event-bus-first architecture.
- [x] `app/domain/volunteer_applications/workflow.py` added as the lifecycle coordinator.
- [x] `app/domain/volunteer_applications/side_effects.py` added for cache/email/photo cleanup side effects.
- [x] Volunteer document UI/service/repository/media/storage surface removed.
- [x] Supabase Storage media support removed; personnel photos use Azure Blob Storage.
- [x] `SimpleEventBus` kept as a narrow tested utility, but removed from the volunteer application control flow.
- [x] `groups/queries.py` added for group admin read/statistics behavior; `groups/service.py` keeps writes.

### Architecture
```
VolunteerApplicationsService facade
    -> VolunteerApplicationWorkflow
        -> record/transition operation
        -> named side-effect method
```

### Next phases
- Extract volunteer role assignments into a dedicated domain module after the document cleanup settles.
