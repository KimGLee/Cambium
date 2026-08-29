## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]].
- Next: [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|Cross-page and Control-plane Dimension Map]].

## Purpose

This module owns what a receipt must prove to be consumed as current authorization for a Gate ID, and who may record one when the registered producer is `manual-attestation`. It adds no Gate ID, judgment item, reuse rule, or receipt dimension. Field meanings and reuse remain with K12/07; Gate IDs and producer protocols remain with K00/12.

## Gate Receipt Payload

The registered Gate-receipt machine contract is the sole normative source for fields, shapes, closed values, conditional requirements, and serialization. This page owns their semantic boundary. A receipt offered as current Gate authorization must bind:

- one append-only receipt identity and the exact Gate ID;
- the current registered producer capability and protocol identity;
- the admitted dimension, exact target, passing result, concrete evidence
  statement, and verification time;
- a clear non-invalidated state;
- the task, Standards, and selected Profile identities that existed when the
  evidence was produced, where canonical task runtime exists.

A bare "QA passed" statement is insufficient. Identity fields describe what the producer actually observed. Where no canonical Queue exists they are omitted rather than filled with null claims. Candidate `profile-load` evidence binds the candidate manifest without mixing it with a live before-task identity; current-use Profile evidence binds the live task identities normally.

A Gate owner may require stronger bindings. Batch Review binds its batch, Delta page evidence, and any frozen Profile judgment set. Batch close binds its repository snapshot and member chain. `profile-load` binds the Profile tree, typed dependency closure, and root-owned interface inputs. A Gate consuming a Profile-derived machine artifact also binds the exact artifact bytes and the same Profile authority context. Terminal Proof binds the repository snapshot observed by that Terminal decision. These additions are owned by the respective Gate contracts and do not create alternative receipt schemas here.

Changed identity makes a receipt historical rather than current authorization. The same bytes reached through a different Profile or compiled from a different authority context are not transferable evidence.

## Standards-adoption Boundary Authority

A current raw receipt proves only its registered Gate. It does not acquire Standards-adoption authority because a plan names that Gate as affected. The [[kernel/K00 Standards Control/12 Control Registry#Standards Revalidation Capability Registry|Standards Revalidation Capability Registry]] is the sole leaf-to-owner projection:

- semantic-leaf evidence is member evidence for its registered owner and cannot
  directly authorize an adoption boundary;
- a native-owner receipt authorizes only its ordinary lifecycle edge;
- `required-queue-consistency` is the immediate owner available to the
  post-adoption aggregate;
- `profile-load` is consumed only as candidate after-image admission;
- mechanism-only, unsupported, and advisory evidence never becomes blocking
  boundary authorization.

An owner receipt does not erase its leaves. Its contract binds the exact member receipts, scope, and fingerprints required for that decision. A revalidation aggregate may record native owners deferred to their transitions but cannot manufacture those owner receipts or upgrade a raw leaf.

These rules govern new current authorization. A historical transition and its aggregate replay under the producer-era protocol they recorded; immutable historical evidence is not rejected for lacking fields or owner links added later.

## Recording Authority

The actor recording a `manual-attestation` receipt must hold the semantic authority named by the Gate owner. Where the owner names none, the selected Profile's gatekeeper role supplies the authority; a Profile extension Gate uses its registered pass-authority role. One actor may hold several roles, subject to any explicit independence rule at the consuming boundary.

This constrains who may attest but does not authenticate the actor. The trust boundary remains the one stated by K12/16.

## Consumption And Rejection

The Control Registry decides which boundary may consume each Gate ID. A consumer resolves only current catalog evidence and rejects an unregistered Gate or producer protocol, non-passing result, invalidated record, stale task or Profile identity, insufficient owner-specific bindings, or evidence predating the obligation it is offered against.

Rejection removes current authorization, not the record. Receipts remain immutable history for the claims they still support under K12/07.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
