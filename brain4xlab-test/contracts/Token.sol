pragma solidity 0.7.0;

import "./IERC20.sol";
import "./IMintableToken.sol";
import "./IDividends.sol";
import "./SafeMath.sol";

contract Token is IERC20, IMintableToken, IDividends {
  // ------------------------------------------ //
  // ----- BEGIN: DO NOT EDIT THIS SECTION ---- //
  // ------------------------------------------ //
  using SafeMath for uint256;
  uint256 public totalSupply;
  uint256 public decimals = 18;
  string public name = "Test token";
  string public symbol = "TEST";
  mapping (address => uint256) public balanceOf;
  // ------------------------------------------ //
  // ----- END: DO NOT EDIT THIS SECTION ------ //  
  // ------------------------------------------ //

  event Transfer(address indexed from, address indexed to, uint256 value);
  event Approval(address indexed owner, address indexed spender, uint256 value);

  mapping(address => mapping(address => uint256)) private _allowances;
  
  // Dividend tracking
  uint256 private constant MAGNITUDE = 10**18;
  uint256 private _totalDividendPerToken;
  mapping(address => uint256) private _lastDividendPerToken;
  mapping(address => uint256) private _dividendEarned;

  // Holder list management
  address[] private _holders;
  mapping(address => uint256) private _holderIndex; // 1-indexed

  // IERC20

  function allowance(address owner, address spender) external view override returns (uint256) {
    return _allowances[owner][spender];
  }

  function transfer(address to, uint256 value) external override returns (bool) {
    _transfer(msg.sender, to, value);
    return true;
  }

  function approve(address spender, uint256 value) external override returns (bool) {
    _allowances[msg.sender][spender] = value;
    emit Approval(msg.sender, spender, value);
    return true;
  }

  function transferFrom(address from, address to, uint256 value) external override returns (bool) {
    _allowances[from][msg.sender] = _allowances[from][msg.sender].sub(value, "SafeMath: transfer amount exceeds allowance");
    _transfer(from, to, value);
    return true;
  }

  // IMintableToken

  function mint() external payable override {
    require(msg.value > 0, "Mint value must be > 0");
    _updateDividend(msg.sender);
    balanceOf[msg.sender] = balanceOf[msg.sender].add(msg.value);
    totalSupply = totalSupply.add(msg.value);
    _addHolder(msg.sender);
    emit Transfer(address(0), msg.sender, msg.value);
  }

  function burn(address payable dest) external override {
    uint256 value = balanceOf[msg.sender];
    require(value > 0, "No tokens to burn");
    _updateDividend(msg.sender);
    
    balanceOf[msg.sender] = 0;
    totalSupply = totalSupply.sub(value);
    _removeHolder(msg.sender);
    emit Transfer(msg.sender, address(0), value);
    
    dest.transfer(value);
  }

  // IDividends

  function getNumTokenHolders() external view override returns (uint256) {
    return _holders.length;
  }

  function getTokenHolder(uint256 index) external view override returns (address) {
    if (index == 0 || index > _holders.length) return address(0);
    return _holders[index - 1];
  }

  function recordDividend() external payable override {
    require(msg.value > 0, "Dividend must be > 0");
    require(totalSupply > 0, "No tokens to distribute to");
    _totalDividendPerToken = _totalDividendPerToken.add(msg.value.mul(MAGNITUDE).div(totalSupply));
  }

  function getWithdrawableDividend(address payee) public view override returns (uint256) {
    uint256 newDividends = balanceOf[payee].mul(_totalDividendPerToken.sub(_lastDividendPerToken[payee])).div(MAGNITUDE);
    return _dividendEarned[payee].add(newDividends);
  }

  function withdrawDividend(address payable dest) external override {
    _updateDividend(msg.sender);
    uint256 amount = _dividendEarned[msg.sender];
    require(amount > 0, "No dividend to withdraw");
    _dividendEarned[msg.sender] = 0;
    dest.transfer(amount);
  }

  // Internal

  function _transfer(address from, address to, uint256 value) internal {
    require(to != address(0), "Transfer to zero address");
    _updateDividend(from);
    _updateDividend(to);
    
    balanceOf[from] = balanceOf[from].sub(value, "SafeMath: transfer amount exceeds balance");
    balanceOf[to] = balanceOf[to].add(value);
    
    if (balanceOf[from] == 0) _removeHolder(from);
    _addHolder(to);
    
    emit Transfer(from, to, value);
  }

  function _updateDividend(address account) internal {
    _dividendEarned[account] = getWithdrawableDividend(account);
    _lastDividendPerToken[account] = _totalDividendPerToken;
  }

  function _addHolder(address account) internal {
    if (balanceOf[account] > 0 && _holderIndex[account] == 0) {
      _holders.push(account);
      _holderIndex[account] = _holders.length;
    }
  }

  function _removeHolder(address account) internal {
    if (balanceOf[account] == 0 && _holderIndex[account] != 0) {
      uint256 index = _holderIndex[account];
      uint256 lastIndex = _holders.length;
      address lastHolder = _holders[lastIndex - 1];
      
      _holders[index - 1] = lastHolder;
      _holderIndex[lastHolder] = index;
      
      _holders.pop();
      delete _holderIndex[account];
    }
  }
}