import React from 'react';
import './ArchiveForm.css';

class ArchiveFormComponent extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      newUrl: '',
      maxPages: 25
    };
  }

  handleSubmit = async (e) => {
    e.preventDefault();
    if (!this.state.newUrl.trim()) return;

    const result = await this.props.onArchiveSubmit(this.state.newUrl, this.state.maxPages);
    if (result.success) {
      alert('Archive started!');
      this.setState({ newUrl: '' });
    } else {
      alert('Failed to start archive');
    }
  };

  handleUrlChange = (e) => {
    this.setState({ newUrl: e.target.value });
  };

  handleMaxPagesChange = (e) => {
    this.setState({ maxPages: parseInt(e.target.value, 10) });
  };

  render() {
    const { isArchiving } = this.props;
    const { newUrl, maxPages } = this.state;

    return (
      <section className="archive-section">
        <h2>Archive a New URL</h2>
        <form onSubmit={this.handleSubmit} className="archive-form">
          <input
            type="url"
            value={newUrl}
            onChange={this.handleUrlChange}
            placeholder="Enter URL to archive (e.g., https://example.com)"
            required
            disabled={isArchiving}
          />

          <div className="range-wrap">
            <label htmlFor="max-pages" className="range-label">
              How many pages: <span className="range-value">{maxPages}</span>
            </label>
            <input
              id="max-pages"
              type="range"
              min={10}
              max={1000}
              step={10}
              value={maxPages}
              onChange={this.handleMaxPagesChange}
              disabled={isArchiving}
            />
          </div>

          <button className="standard-button-main" type="submit" disabled={isArchiving}>
            {isArchiving ? 'Archiving...' : 'Archive Site'}
          </button>
        </form>
      </section>
    );
  }
}

export default ArchiveFormComponent;