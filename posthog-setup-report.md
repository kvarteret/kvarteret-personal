<wizard-report>
# PostHog post-wizard report

The wizard has completed a deep integration of PostHog analytics into the Kvarteret Personal FastAPI application. PostHog is initialized in the app lifespan (`app/runtime.py`) using credentials from environment variables, and flushes buffered events on shutdown. Ten events are captured across six route files, covering the full volunteer onboarding funnel, user authentication, feedback submissions, and admin volunteer-management actions. Each server-side event identifies the acting user via their stable `auth_user_id` UUID using `new_context()` / `identify_context()` from the PostHog context API.

| Event | Description | File |
|---|---|---|
| `user_logged_in` | Fired after a user successfully logs in | `app/web/routes/auth/routes.py` |
| `user_logged_out` | Fired when an authenticated user logs out | `app/web/routes/auth/routes.py` |
| `volunteer_application_invite_created` | Fired when an admin creates a new volunteer invite | `app/web/routes/volunteer_applications/actions.py` |
| `volunteer_application_submitted` | Fired when an applicant submits their application form | `app/web/routes/volunteer_applications/actions.py` |
| `volunteer_application_approved` | Fired when a volunteer application is approved | `app/web/routes/volunteer_applications/actions.py` |
| `volunteer_application_deleted` | Fired when a volunteer application is deleted/rejected | `app/web/routes/volunteer_applications/actions.py` |
| `feedback_submitted` | Fired on successful feedback submission (ris/ros/forslag) | `app/web/routes/feedback/routes.py` |
| `volunteer_role_assignment_added` | Fired when an admin assigns a role to a volunteer | `app/web/routes/volunteers/actions.py` |
| `volunteer_course_completion_added` | Fired when an admin records a course completion | `app/web/routes/volunteers/actions.py` |
| `volunteer_deleted` | Fired when an admin deletes a volunteer record | `app/web/routes/volunteers/actions.py` |

## Next steps

We've built some insights and a dashboard for you to keep an eye on user behavior, based on the events we just instrumented:

- **Dashboard — Analytics basics**: https://eu.posthog.com/project/156267/dashboard/613281
- **Volunteer onboarding funnel** (invite → submitted → approved): https://eu.posthog.com/project/156267/insights/UZAwX4iD
- **Daily active logins**: https://eu.posthog.com/project/156267/insights/T9zZKiGJ
- **Feedback by category** (ris/ros/forslag breakdown): https://eu.posthog.com/project/156267/insights/f3efmCV1
- **Application outcomes: approved vs. rejected**: https://eu.posthog.com/project/156267/insights/rw8PSPXb
- **Volunteer record activity** (role assignments & course completions): https://eu.posthog.com/project/156267/insights/eKyTLbFp

### Agent skill

We've left an agent skill folder in your project. You can use this context for further agent development when using Claude Code. This will help ensure the model provides the most up-to-date approaches for integrating PostHog.

</wizard-report>
