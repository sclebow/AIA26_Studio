import { Component } from "react";

// Catches render/effect errors in a subtree so one broken feature (e.g. the 3D
// galaxy) shows a message instead of blanking the whole app.
export default class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("[ErrorBoundary]", error, info); }
  render() {
    if (this.state.error) {
      return this.props.fallback
        ? this.props.fallback(this.state.error, () => this.setState({ error: null }))
        : null;
    }
    return this.props.children;
  }
}
